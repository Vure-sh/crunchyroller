"""
crunchyroller discord bot — remote control for the downloader from your phone.
reuses the same download pipeline as web_gui.py, with organized episode selection,
strict chronological ordering, live Discord status updates, and real-time auto-updating /status dashboard.
"""

import asyncio
import os
import socket
import sys
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Set

# Ensure project root is in sys.path when run as standalone script
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import discord
from discord import app_commands

from crunchyroll.api import (
    get_episode_info,
    get_season_episodes,
    get_seasons,
    get_series,
    parse_url_type,
)
from crunchyroll.auth import load_config
from crunchyroll.downloader import download_episode
from crunchyroll.http_client import CrunchyrollHttpClient
from crunchyroll.types import EpisodeInfo, EpisodeMetadata, Season, SeasonEpisode


# ── single instance socket lock ──────────────────────────────────────────────

_LOCK_SOCKET = None

def acquire_instance_lock() -> bool:
    """prevent multiple competing bot instances from running simultaneously"""
    global _LOCK_SOCKET
    try:
        _LOCK_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _LOCK_SOCKET.bind(("127.0.0.1", 54321))
        return True
    except socket.error:
        return False


# ── state ────────────────────────────────────────────────────────────────────

class DownloadState:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "idle"  # idle | running | completed | failed
        self.progress = 0.0
        self.episode = ""
        self.error = ""
        self.current_seg = 0
        self.total_segs = 0
        self.speed = "0.0 MB/s"
        self.vq = ""
        self.aq = ""
        self.start_time = 0.0
        self.cancel_flag = False
        self.queue: deque = deque()  # list of dicts with episode info & channel_id
        self.worker_thread = None  # current _worker_loop thread, if any
        self.log: list = []

    def _log(self, msg: str):
        with self.lock:
            self.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            if len(self.log) > 100:
                self.log.pop(0)

    def reset(self):
        with self.lock:
            self.status = "idle"
            self.progress = 0.0
            self.episode = ""
            self.error = ""
            self.current_seg = 0
            self.total_segs = 0
            self.speed = "0.0 MB/s"
            self.start_time = 0.0
            self.cancel_flag = False


STATE = DownloadState()


# ── discord notification helper ──────────────────────────────────────────────

async def _async_send_msg(channel_id: int, text: str):
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
        if channel:
            await channel.send(text)
    except Exception as e:
        print(f"Failed to send Discord message: {e}")


def notify_discord(channel_id: Optional[int], text: str):
    """safely dispatch a message to a discord channel from the worker thread"""
    if channel_id and bot.is_ready() and bot.loop and not bot.is_closed():
        asyncio.run_coroutine_threadsafe(_async_send_msg(channel_id, text), bot.loop)


# ── progress bar & embed builder ─────────────────────────────────────────────

def make_progress_bar(percent: float, length: int = 14) -> str:
    """generates a sleek modern progress bar string"""
    filled = int(round(length * (percent / 100.0)))
    filled = max(0, min(length, filled))
    unfilled = length - filled
    return f"`[{'▰' * filled}{'▱' * unfilled}]` **{percent:.1f}%**"


def build_status_embed() -> discord.Embed:
    """builds an aesthetic, real-time status embed card"""
    with STATE.lock:
        status = STATE.status
        progress = STATE.progress
        episode = STATE.episode
        error = STATE.error
        cur_seg = STATE.current_seg
        tot_seg = STATE.total_segs
        speed = STATE.speed
        vq = STATE.vq
        aq = STATE.aq
        elapsed = int(time.time() - STATE.start_time) if (STATE.start_time > 0 and status == "running") else 0
        q = list(STATE.queue)
        recent_log = list(STATE.log[-4:])

    if status == "running":
        embed = discord.Embed(
            title="⚡ Live Download Progress",
            description=f"📺 **{episode}**\n\n{make_progress_bar(progress)}",
            color=0x5865F2,
        )
        if tot_seg > 0:
            embed.add_field(name="📦 Segments", value=f"`{cur_seg} / {tot_seg}`", inline=True)
        if speed and speed != "0.0 MB/s":
            embed.add_field(name="🚀 Speed", value=f"`{speed}`", inline=True)
        if elapsed > 0:
            mins, secs = divmod(elapsed, 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            embed.add_field(name="⏱️ Elapsed", value=f"`{time_str}`", inline=True)
        if vq and aq:
            embed.add_field(name="⚙️ Quality", value=f"`{vq} / {aq}`", inline=True)
        embed.add_field(name="📋 In Queue", value=f"`{len(q)}` episode(s) waiting", inline=True)

        if recent_log:
            embed.add_field(
                name="📜 Recent Activity",
                value="```" + "\n".join(recent_log) + "```",
                inline=False,
            )
        embed.set_footer(text="🟢 Auto-updating live • Use buttons below to refresh or cancel")

    elif status == "completed":
        embed = discord.Embed(
            title="✅ Download Finished",
            description=f"📺 **{episode}**\n\n{make_progress_bar(100.0)}\n\n✨ File saved and muxed to MKV successfully!",
            color=0x57F287,
        )
        embed.add_field(name="📋 Queue", value=f"`{len(q)}` episode(s) waiting", inline=True)
        embed.set_footer(text="Crunchyroller Bot • Idle")

    elif status == "failed":
        embed = discord.Embed(
            title="❌ Download Failed",
            description=f"📺 **{episode}**\n\n> **Error:** `{error}`",
            color=0xED4245,
        )
        embed.add_field(name="📋 Queue", value=f"`{len(q)}` episode(s) remaining", inline=True)
        embed.set_footer(text="Crunchyroller Bot • Idle")

    else:
        embed = discord.Embed(
            title="💤 Downloader Idle",
            description=(
                "No downloads currently in progress.\n\n"
                "• Send **/download <url>** to start downloading.\n"
                "• Or check queued episodes with **/queue**."
            ),
            color=0x2B2D31,
        )
        if q:
            embed.add_field(
                name="📋 Queued Up Next",
                value=f"**{len(q)}** episode(s) waiting in queue",
                inline=False,
            )
            next_items = [f"`{i+1}.` {item['label']}" for i, item in enumerate(q[:5])]
            embed.add_field(
                name="Next in line",
                value="\n".join(next_items),
                inline=False,
            )
        embed.set_footer(text="Crunchyroller Bot • Ready")

    return embed


class LiveStatusView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.is_stopped = False

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_status_embed(), view=self)

    @discord.ui.button(label="🛑 Cancel Download", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        with STATE.lock:
            STATE.cancel_flag = True
            STATE.queue.clear()
            STATE.status = "idle"
            STATE.episode = ""
        self.is_stopped = True
        await interaction.response.edit_message(
            content="🛑 **Download cancelled and queue cleared.**",
            embed=build_status_embed(),
            view=None,
        )

    @discord.ui.button(label="📋 View Queue", style=discord.ButtonStyle.primary)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        with STATE.lock:
            q = list(STATE.queue)
        if not q:
            await interaction.response.send_message("📋 Queue is empty.", ephemeral=True)
            return
        lines = [f"📋 **Queued Episodes ({len(q)}):**"]
        for i, item in enumerate(q[:15]):
            lines.append(f"`{i+1}.` {item['label']}")
        if len(q) > 15:
            lines.append(f"*...and {len(q) - 15} more*")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ── download worker ──────────────────────────────────────────────────────────

def _worker_loop(etp_rt: str):
    """process queued items one by one in exact order"""
    total_batch = 0
    success_count = 0
    fail_count = 0
    last_channel_id = None

    while True:
        with STATE.lock:
            if STATE.cancel_flag:
                STATE.queue.clear()
                STATE.status = "idle"
                STATE.cancel_flag = False
                if STATE.worker_thread is threading.current_thread():
                    STATE.worker_thread = None
                return

            if not STATE.queue:
                STATE.status = "idle"
                if STATE.worker_thread is threading.current_thread():
                    STATE.worker_thread = None
                if total_batch > 1 and last_channel_id:
                    notify_discord(
                        last_channel_id,
                        f"🎉 **Batch Download Finished!** (`{success_count}` successful, `{fail_count}` failed)",
                    )
                return

            item = STATE.queue.popleft()

        total_batch += 1
        ep_id = item["ep_id"]
        label = item["label"]
        vq = item["vq"]
        aq = item["aq"]
        a_langs = item["a_langs"]
        s_langs = item["s_langs"]
        channel_id = item.get("channel_id")
        last_channel_id = channel_id

        with STATE.lock:
            STATE.status = "running"
            STATE.progress = 0.0
            STATE.episode = label
            STATE.current_seg = 0
            STATE.total_segs = 0
            STATE.speed = "0.0 MB/s"
            STATE.vq = vq
            STATE.aq = aq
            STATE.start_time = time.time()
            STATE.error = ""

        STATE._log(f"downloading: {label}")
        notify_discord(channel_id, f"⏳ **Downloading:** `{label}` `[{vq}/{aq}]`")

        try:
            client = CrunchyrollHttpClient(etp_rt)
            info = get_episode_info(client, ep_id)

            def _cb(title, cur, tot, speed, status):
                with STATE.lock:
                    STATE.current_seg = cur
                    STATE.total_segs = tot
                    STATE.speed = speed
                    STATE.progress = round((cur / tot) * 100, 1) if tot > 0 else 0
                    STATE.episode = label

            output_file = download_episode(
                client=client,
                base_content_id=ep_id,
                info=info,
                audio_langs=a_langs,
                subs_langs=s_langs,
                video_quality=vq,
                audio_quality=aq,
                progress_cb=_cb,
            )

            # verify the file actually exists on disk
            if output_file and os.path.exists(output_file) and os.path.getsize(output_file) > 1024:
                file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
                success_count += 1
                with STATE.lock:
                    STATE.status = "completed"
                    STATE.progress = 100.0
                STATE._log(f"done: {label} ({file_size_mb:.1f} MB)")
                notify_discord(
                    channel_id,
                    f"✅ **Download Complete:** `{label}` `({file_size_mb:.1f} MB)`",
                )
            else:
                raise RuntimeError(
                    f"Download finished but output file was not found or is 0 bytes: {output_file}"
                )

        except Exception as e:
            fail_count += 1
            err_msg = str(e)
            with STATE.lock:
                STATE.status = "failed"
                STATE.error = err_msg
            STATE._log(f"failed: {label} — {err_msg}")
            notify_discord(
                channel_id,
                f"❌ **Download Failed:** `{label}`\n> **Error:** `{err_msg}`",
            )


def enqueue_episodes(items: List[dict], etp_rt: str):
    """add items to queue in exact sequence and start worker if needed"""
    with STATE.lock:
        for item in items:
            STATE.queue.append(item)

        worker = STATE.worker_thread
        worker_alive = worker is not None and worker.is_alive()

        # Start a worker only when no live worker exists. Checking the thread
        # handle (rather than STATE.status) prevents a second worker from racing
        # on STATE.queue during the window where a finishing worker has set its
        # status to "completed"/"failed" but has not yet returned.
        if not worker_alive:
            t = threading.Thread(target=_worker_loop, args=(etp_rt,), daemon=True)
            STATE.worker_thread = t
            t.start()


# ── range parser helper ──────────────────────────────────────────────────────

def parse_episode_ranges(range_str: str, available_eps: List[SeasonEpisode]) -> List[SeasonEpisode]:
    """parse expressions like '1-5, 8, 10-12', 'all', '1, 3, 5' and return matching episodes strictly in numerical order"""
    raw = range_str.strip().lower()
    if raw in ("all", "*", "everything", "full"):
        return list(available_eps)

    selected_set = set()
    ep_map = {ep.episode_number: ep for ep in available_eps}

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            sub = part.split("-")
            if len(sub) == 2:
                try:
                    start, end = int(sub[0].strip()), int(sub[1].strip())
                    for num in range(min(start, end), max(start, end) + 1):
                        if num in ep_map:
                            selected_set.add(num)
                except ValueError:
                    pass
        else:
            try:
                num = int(part)
                if num in ep_map:
                    selected_set.add(num)
            except ValueError:
                pass

    # return strictly preserving the order in available_eps
    return [ep for ep in available_eps if ep.episode_number in selected_set]


# ── interactive ui views ─────────────────────────────────────────────────────

class CustomRangeModal(discord.ui.Modal, title="Select Episode Range"):
    def __init__(self, picker_view: "EpisodePickerView"):
        super().__init__()
        self.picker_view = picker_view
        eps = self.picker_view.current_episodes
        min_ep = eps[0].episode_number if eps else 1
        max_ep = eps[-1].episode_number if eps else len(eps)

        self.range_input = discord.ui.TextInput(
            label=f"Episode Range ({min_ep} - {max_ep} available)",
            placeholder="e.g. 1-5, 8, 11-13  or  all",
            required=True,
            max_length=100,
        )
        self.add_item(self.range_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.range_input.value.strip()
        eps = parse_episode_ranges(raw, self.picker_view.current_episodes)
        if not eps:
            await interaction.response.send_message(
                f"❌ No matching episodes found for `{raw}` in this season.",
                ephemeral=True,
            )
            return
        await self.picker_view.enqueue_and_finish(interaction, eps)


class SingleEpisodeView(discord.ui.View):
    def __init__(
        self,
        ep_id: str,
        label: str,
        series_id: Optional[str],
        vq: str,
        aq: str,
        a_langs: List[str],
        s_langs: List[str],
        etp_rt: str,
    ):
        super().__init__(timeout=300)
        self.ep_id = ep_id
        self.label = label
        self.series_id = series_id
        self.vq = vq
        self.aq = aq
        self.a_langs = a_langs
        self.s_langs = s_langs
        self.etp_rt = etp_rt

    @discord.ui.button(label="📥 Download This Episode", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        item = {
            "ep_id": self.ep_id,
            "label": self.label,
            "vq": self.vq,
            "aq": self.aq,
            "a_langs": self.a_langs,
            "s_langs": self.s_langs,
            "channel_id": interaction.channel_id,
        }
        enqueue_episodes([item], self.etp_rt)
        self.clear_items()
        await interaction.response.edit_message(
            content=f"📥 **Queued for download:**\n`1.` {self.label} `[{self.vq}/{self.aq}]`",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.clear_items()
        await interaction.response.edit_message(
            content="❌ Cancelled.",
            embed=None,
            view=None,
        )


class EpisodePickerView(discord.ui.View):
    def __init__(
        self,
        series_title: str,
        seasons: List[Season],
        season_episodes_map: Dict[str, List[SeasonEpisode]],
        vq: str,
        aq: str,
        a_langs: List[str],
        s_langs: List[str],
        etp_rt: str,
    ):
        super().__init__(timeout=300)
        self.series_title = series_title
        self.seasons = seasons
        self.season_episodes_map = season_episodes_map
        self.current_season_idx = 0
        self.selected_ep_ids: Set[str] = set()
        self.vq = vq
        self.aq = aq
        self.a_langs = a_langs
        self.s_langs = s_langs
        self.etp_rt = etp_rt
        self.update_components()

    @property
    def current_season(self) -> Season:
        return self.seasons[self.current_season_idx]

    @property
    def current_episodes(self) -> List[SeasonEpisode]:
        sn = self.current_season
        return self.season_episodes_map.get(sn.id, [])

    def update_components(self):
        self.clear_items()

        # 1. Season selector dropdown (if series has multiple seasons)
        if len(self.seasons) > 1:
            season_options = [
                discord.SelectOption(
                    label=f"Season {s.season_number}: {s.title or 'Season ' + str(s.season_number)}"[:100],
                    value=str(i),
                    default=(i == self.current_season_idx),
                )
                for i, s in enumerate(self.seasons[:25])
            ]
            season_select = discord.ui.Select(
                placeholder="Switch Season...",
                options=season_options,
                row=0,
            )
            season_select.callback = self.on_season_change
            self.add_item(season_select)

        # 2. Episode multi-select dropdown (up to 25 items in numerical order)
        eps = self.current_episodes
        if eps:
            ep_options = [
                discord.SelectOption(
                    label=f"E{ep.episode_number:02d}: {ep.title or 'Episode ' + str(ep.episode_number)}"[:100],
                    description=f"Season {ep.season_number} Episode {ep.episode_number}"[:50],
                    value=ep.id,
                    default=(ep.id in self.selected_ep_ids),
                )
                for ep in eps[:25]
            ]
            ep_select = discord.ui.Select(
                placeholder="Choose specific episode(s)...",
                min_values=1,
                max_values=len(ep_options),
                options=ep_options,
                row=1,
            )
            ep_select.callback = self.on_episode_select
            self.add_item(ep_select)

        # 3. Action buttons
        btn_range = discord.ui.Button(
            label="🔢 Select Range (e.g. 1-5)",
            style=discord.ButtonStyle.primary,
            row=2,
        )
        btn_range.callback = self.on_custom_range
        self.add_item(btn_range)

        btn_download_selected = discord.ui.Button(
            label="📥 Download Selected",
            style=discord.ButtonStyle.success,
            row=2,
        )
        btn_download_selected.callback = self.on_download_selected
        self.add_item(btn_download_selected)

        btn_download_all = discord.ui.Button(
            label="📦 Download Full Season",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        btn_download_all.callback = self.on_download_all
        self.add_item(btn_download_all)

        btn_cancel = discord.ui.Button(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            row=2,
        )
        btn_cancel.callback = self.on_cancel
        self.add_item(btn_cancel)

    def build_embed(self) -> discord.Embed:
        eps = self.current_episodes
        sn = self.current_season
        min_ep = eps[0].episode_number if eps else 1
        max_ep = eps[-1].episode_number if eps else len(eps)

        embed = discord.Embed(
            title=f"🎬 {self.series_title}",
            description=(
                f"**Season {sn.season_number}** • `{len(eps)} Episodes Available` (Episodes {min_ep} to {max_ep})\n"
                f"Quality: `{self.vq}` / `{self.aq}`\n\n"
                f"**How to pick:**\n"
                f"• Tap **🔢 Select Range** to type ranges like `1-5` or `1, 3, 5`\n"
                f"• Or choose specific episodes from the dropdown below\n"
                f"• Or tap **📦 Download Full Season**"
            ),
            color=0x5865F2,
        )
        if self.selected_ep_ids:
            # show in exact chronological order
            ordered_selected = [ep for ep in eps if ep.id in self.selected_ep_ids]
            embed.add_field(
                name="Checked from Dropdown",
                value=f"**{len(ordered_selected)}** episode(s) (E{', E'.join(str(e.episode_number) for e in ordered_selected[:10])})",
                inline=False,
            )
        return embed

    async def on_season_change(self, interaction: discord.Interaction):
        self.current_season_idx = int(interaction.data["values"][0])
        self.selected_ep_ids.clear()
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_episode_select(self, interaction: discord.Interaction):
        self.selected_ep_ids = set(interaction.data["values"])
        self.update_components()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_download_selected(self, interaction: discord.Interaction):
        if not self.selected_ep_ids:
            await interaction.response.send_message(
                "❌ Select episodes from the dropdown first, or click **Select Range** to type numbers!",
                ephemeral=True,
            )
            return
        # STRICT CHRONOLOGICAL ORDER: match order in current_episodes (E1, E2, E3...)
        selected_eps = [ep for ep in self.current_episodes if ep.id in self.selected_ep_ids]
        await self.enqueue_and_finish(interaction, selected_eps)

    async def on_download_all(self, interaction: discord.Interaction):
        await self.enqueue_and_finish(interaction, self.current_episodes)

    async def on_custom_range(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CustomRangeModal(self))

    async def on_cancel(self, interaction: discord.Interaction):
        self.clear_items()
        await interaction.response.edit_message(
            content="❌ Download cancelled.",
            embed=None,
            view=None,
        )

    async def enqueue_and_finish(
        self, interaction: discord.Interaction, episodes: List[SeasonEpisode]
    ):
        if not episodes:
            await interaction.response.send_message(
                "❌ No episodes selected.", ephemeral=True
            )
            return

        queue_items = []
        for ep in episodes:
            lbl = f"{self.series_title} S{ep.season_number:02d}E{ep.episode_number:02d} — {ep.title}"
            queue_items.append({
                "ep_id": ep.id,
                "label": lbl,
                "vq": self.vq,
                "aq": self.aq,
                "a_langs": self.a_langs,
                "s_langs": self.s_langs,
                "channel_id": interaction.channel_id,
            })

        enqueue_episodes(queue_items, self.etp_rt)

        lines = [
            f"📥 **Queued {len(queue_items)} episode(s) in order** `[{self.vq}/{self.aq}]`:"
        ]
        for i, item in enumerate(queue_items[:10]):
            lines.append(f"`{i+1}.` {item['label']}")
        if len(queue_items) > 10:
            lines.append(f"*...and {len(queue_items) - 10} more*")

        self.clear_items()
        if interaction.response.is_done():
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                content="\n".join(lines),
                embed=None,
                view=None,
            )
        else:
            await interaction.response.edit_message(
                content="\n".join(lines),
                embed=None,
                view=None,
            )


# ── discord bot ──────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


@bot.event
async def on_ready():
    await tree.sync()
    print(f"bot ready as {bot.user}")


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"App command error: {error}")
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ An error occurred: `{error}`", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ An error occurred: `{error}`", ephemeral=True)
    except Exception:
        pass


@tree.command(name="download", description="submit a crunchyroll url to select and download episodes")
@app_commands.describe(url="crunchyroll episode, season, or series url")
async def cmd_download(interaction: discord.Interaction, url: str):
    # IMMEDIATELY DEFER to prevent 3-second Discord interaction timeout
    await interaction.response.defer(ephemeral=False)

    cfg = load_config()
    etp_rt = cfg.get("etp_rt", "")
    if not etp_rt:
        await interaction.followup.send(
            "❌ no etp_rt token found in config.json. log in via the desktop app first."
        )
        return

    try:
        kind, cid = parse_url_type(url)
    except ValueError as e:
        await interaction.followup.send(f"❌ {e}")
        return

    vq = cfg.get("video_quality", "1080p")
    aq = cfg.get("audio_quality", "192k")
    al = cfg.get("audio_lang", "ja-JP")
    sl = cfg.get("subs_lang", "en-US")
    a_langs = [x.strip() for x in al.split(",") if x.strip()] or ["ja-JP"]
    s_langs = [x.strip() for x in sl.split(",") if x.strip()] or ["en-US"]
    api_audio = a_langs[0] if a_langs[0].lower() not in {"all", "*"} else "ja-JP"
    api_subs = s_langs[0] if s_langs[0].lower() not in {"all", "*"} else "en-US"

    try:
        client = CrunchyrollHttpClient(etp_rt)

        if kind == "episode":
            info = get_episode_info(client, cid)
            label = (
                f"{info.episode_metadata.series_title} "
                f"S{info.episode_metadata.season_number:02d}E{info.episode_metadata.episode_number:02d} — {info.title}"
            )
            embed = discord.Embed(
                title=f"📺 {info.title}",
                description=(
                    f"**Series:** {info.episode_metadata.series_title}\n"
                    f"**Episode:** S{info.episode_metadata.season_number:02d}E{info.episode_metadata.episode_number:02d}\n"
                    f"**Quality:** `{vq}` / `{aq}`"
                ),
                color=0x5865F2,
            )
            view = SingleEpisodeView(
                ep_id=cid,
                label=label,
                series_id=None,
                vq=vq,
                aq=aq,
                a_langs=a_langs,
                s_langs=s_langs,
                etp_rt=etp_rt,
            )
            await interaction.followup.send(embed=embed, view=view)

        elif kind == "series":
            series_meta = get_series(client, cid, api_audio, api_subs)
            title = series_meta.get("title", cid)
            seasons = series_meta.get("seasons", [])

            if not seasons:
                await interaction.followup.send("❌ No seasons found for this series.")
                return

            season_episodes_map: Dict[str, List[SeasonEpisode]] = {}
            valid_seasons: List[Season] = []

            for s in seasons:
                eps = get_season_episodes(client, s.id, api_audio, api_subs)
                if eps:
                    season_episodes_map[s.id] = eps
                    valid_seasons.append(s)

            if not valid_seasons:
                await interaction.followup.send("❌ No playable episodes found in any season.")
                return

            view = EpisodePickerView(
                series_title=title,
                seasons=valid_seasons,
                season_episodes_map=season_episodes_map,
                vq=vq,
                aq=aq,
                a_langs=a_langs,
                s_langs=s_langs,
                etp_rt=etp_rt,
            )
            await interaction.followup.send(embed=view.build_embed(), view=view)

        elif kind == "season":
            eps = get_season_episodes(client, cid, api_audio, api_subs)
            if not eps:
                await interaction.followup.send("❌ No episodes found for this season.")
                return

            title = eps[0].series_title if eps else "Crunchyroll Season"
            sn_num = eps[0].season_number if eps else 1
            pseudo_season = Season(
                id=cid,
                season_number=sn_num,
                audio_locale=api_audio,
                title=f"Season {sn_num}",
            )
            view = EpisodePickerView(
                series_title=title,
                seasons=[pseudo_season],
                season_episodes_map={cid: eps},
                vq=vq,
                aq=aq,
                a_langs=a_langs,
                s_langs=s_langs,
                etp_rt=etp_rt,
            )
            await interaction.followup.send(embed=view.build_embed(), view=view)

        else:
            await interaction.followup.send(f"❌ unsupported url type: {kind}")

    except Exception as e:
        await interaction.followup.send(f"❌ {e}")


@tree.command(name="status", description="show real-time live updating download dashboard")
async def cmd_status(interaction: discord.Interaction):
    """sends an aesthetic status dashboard that auto-refreshes in real-time"""
    await interaction.response.defer(ephemeral=False)
    view = LiveStatusView()
    embed = build_status_embed()
    msg = await interaction.followup.send(embed=embed, view=view)

    # Live auto-update loop (runs for up to 2.5 minutes while downloading)
    for _ in range(60):
        await asyncio.sleep(2.5)
        if view.is_stopped:
            break
        with STATE.lock:
            is_running = (STATE.status == "running")
        try:
            updated_embed = build_status_embed()
            await interaction.edit_original_response(embed=updated_embed, view=view)
        except Exception:
            break
        if not is_running:
            await asyncio.sleep(1)
            try:
                await interaction.edit_original_response(embed=build_status_embed(), view=view)
            except Exception:
                pass
            break


@tree.command(name="queue", description="show queued downloads")
async def cmd_queue(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    with STATE.lock:
        status = STATE.status
        episode = STATE.episode
        q = list(STATE.queue)

    lines = []
    if status == "running":
        lines.append(f"▶️ **now downloading:** {episode}")

    if q:
        lines.append(f"\n📋 **queued in order ({len(q)}):**")
        for i, item in enumerate(q[:15]):
            lines.append(f"`{i+1}.` {item['label']}")
        if len(q) > 15:
            lines.append(f"*...and {len(q) - 15} more*")
    elif not lines:
        lines.append("📋 queue is empty")

    await interaction.followup.send("\n".join(lines))


@tree.command(name="cancel", description="cancel current download and clear queue")
async def cmd_cancel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    with STATE.lock:
        was_running = STATE.status == "running"
        STATE.cancel_flag = True
        STATE.queue.clear()
        STATE.status = "idle"
        STATE.episode = ""

    if was_running:
        await interaction.followup.send("🛑 cancelled current download and cleared queue")
    else:
        await interaction.followup.send("📋 queue cleared (nothing was running)")


# ── entry point ──────────────────────────────────────────────────────────────

def _load_env():
    """load .env file if it exists (no extra dependency needed)"""
    candidate_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(_PROJECT_ROOT, ".env"),
    ]
    for env_path in candidate_paths:
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            break


def start_bot(token: Optional[str] = None):
    _load_env()
    tk = token or os.environ.get("DISCORD_BOT_TOKEN", "")
    if not tk:
        print("error: set DISCORD_BOT_TOKEN in .env file or as environment variable")
        return

    if not acquire_instance_lock():
        print("⚠️ Another instance of discord_bot.py is already running on this machine! Exiting to prevent dual-instance conflict.")
        sys.exit(0)

    bot.run(tk)


if __name__ == "__main__":
    start_bot()
