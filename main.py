import argparse
import sys
import os
from typing import List

# Ensure pywebview uses PyQt6 on Linux when available
os.environ.setdefault("QT_API", "pyqt6")

class SafeStream:
    def __init__(self, target):
        self._target = target

    def write(self, s):
        if self._target is None:
            return
        try:
            self._target.write(s)
        except (AttributeError, UnicodeEncodeError):
            try:
                enc = getattr(self._target, "encoding", "utf-8") or "utf-8"
                safe_s = s.encode(enc, errors="replace").decode(enc, errors="replace")
                self._target.write(safe_s)
            except Exception:
                pass

    def flush(self):
        if self._target is not None and hasattr(self._target, "flush"):
            try:
                self._target.flush()
            except Exception:
                pass

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    if hasattr(sys.stderr, "reconfigure"):
        try: sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

sys.stdout = SafeStream(sys.stdout)
sys.stderr = SafeStream(sys.stderr)

from crunchyroll.api import get_episode_info, get_season_episodes, get_seasons, parse_url_type
from crunchyroll.auth import load_config, save_config
from crunchyroll.downloader import download_episode, download_season, download_series
from crunchyroll.http_client import CrunchyrollHttpClient
from crunchyroll.session_pool import ConcurrencyConfig


def ensure_webview2() -> None:
    """check if WebView2 is installed, and auto-install it if not"""
    if sys.platform != "win32":
        return

    import winreg

    def is_installed() -> bool:
        # check both HKLM and HKCU, 64-bit and 32-bit registry hives
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ]
        for hive, path in keys:
            try:
                k = winreg.OpenKey(hive, path)
                val, _ = winreg.QueryValueEx(k, "pv")
                winreg.CloseKey(k)
                if val and val != "0.0.0.0":
                    return True
            except Exception:
                pass
        return False

    if is_installed():
        return

    # not installed — download the evergreen bootstrapper and run it silently
    import ctypes
    import tempfile
    import urllib.request
    import subprocess

    answer = ctypes.windll.user32.MessageBoxW(
        0,
        "crunchyroller needs Microsoft Edge WebView2 to run.\n\n"
        "It's a small ~2MB install from Microsoft. Install it now?",
        "Install Required Component",
        0x04 | 0x20  # MB_YESNO | MB_ICONQUESTION
    )
    if answer != 6:  # IDYES
        return

    bootstrapper_url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
    tmp = os.path.join(tempfile.gettempdir(), "MicrosoftEdgeWebview2Setup.exe")
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Downloading WebView2 installer...\n\nClick OK and wait a moment.",
            "Downloading",
            0x40  # MB_ICONINFORMATION
        )
        urllib.request.urlretrieve(bootstrapper_url, tmp)
        subprocess.run([tmp, "/silent", "/install"], check=True)
        ctypes.windll.user32.MessageBoxW(
            0,
            "WebView2 installed successfully! Launching crunchyroller now.",
            "Done",
            0x40
        )
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Auto-install failed: {e}\n\n"
            "Please install manually from:\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/",
            "Install Failed",
            0x10  # MB_ICONERROR
        )


def parse_langs(s: str) -> List[str]:
    """split comma-separated locales"""
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def process_url(client: CrunchyrollHttpClient, url: str, args: argparse.Namespace) -> None:
    """handle a single url (episode, season, or series)"""
    try:
        content_type, content_id = parse_url_type(url)
    except ValueError as e:
        print(f"Invalid URL format: {e}")
        return

    audio_langs = parse_langs(args.audio_lang)
    if not audio_langs:
        audio_langs = ["ja-JP"]

    subs_langs = parse_langs(args.subs_lang)
    primary_audio = audio_langs[0] if audio_langs[0].lower() not in {"all", "*"} else "ja-JP"
    primary_subs = (
        subs_langs[0] if subs_langs and subs_langs[0].lower() not in {"all", "*"} else "en-US"
    )

    video_quality = getattr(args, "quality_video", None) or getattr(args, "video_quality", "1080p")
    audio_quality = getattr(args, "quality_audio", None) or getattr(args, "audio_quality", "192k")

    workers = getattr(args, "workers", 8) or 8
    hedging_enabled = bool(getattr(args, "enable_hedging", False) and not getattr(args, "disable_hedging", False))
    server_index = max(0, getattr(args, "server", 1) - 1)
    concurrency_cfg = ConcurrencyConfig(
        min_workers=min(4, workers),
        max_workers=max(10, workers),
        initial_workers=workers,
        hedging_enabled=hedging_enabled,
    )

    if content_type == "episode":
        info = get_episode_info(client, content_id)
        download_episode(
            client,
            content_id,
            info,
            audio_langs,
            subs_langs,
            video_quality,
            audio_quality,
            debug=args.debug_manifest,
            concurrency_config=concurrency_cfg,
            force_download=getattr(args, "force_download", False),
            server_index=server_index,
        )
    elif content_type == "series":
        download_series(
            client,
            content_id,
            audio_langs,
            subs_langs,
            video_quality,
            audio_quality,
            season_filter=args.season,
            debug=args.debug_manifest,
            concurrency_config=concurrency_cfg,
            force_download=getattr(args, "force_download", False),
            server_index=server_index,
        )
    elif content_type == "season":
        episodes = get_season_episodes(client, content_id, primary_audio, primary_subs)
        download_season(
            client,
            video_quality,
            audio_quality,
            audio_langs,
            subs_langs,
            episodes,
            debug=args.debug_manifest,
            concurrency_config=concurrency_cfg,
            force_download=getattr(args, "force_download", False),
            server_index=server_index,
        )


def prompt_star_if_first_run() -> None:
    """Friendly one-time prompt to star the repo on GitHub."""
    try:
        cfg = load_config()
        if not cfg.get("has_seen_star_prompt"):
            print(
                "\n"
                "  ⭐ Enjoying crunchyroller? Please consider giving it a star on GitHub:\n"
                "     https://github.com/Vure-sh/crunchyroller\n"
            )
            save_config({"has_seen_star_prompt": True})
    except Exception:
        pass


def main() -> None:
    prompt_star_if_first_run()
    parser = argparse.ArgumentParser(
        description="Downloads anime from Crunchyroll and outputs them in an MKV file."
    )
    parser.add_argument("--gui", action="store_true", help="Launch native desktop GUI app")
    parser.add_argument("--browser", action="store_true", help="Force opening GUI in default web browser instead of native app window")
    parser.add_argument("--email", type=str, default="", help="User email address")
    parser.add_argument("--password", type=str, default="", help="User password")
    parser.add_argument("--url", type=str, default="", help="URL of the episode/season/series to download")
    parser.add_argument("--file", type=str, default="", help="Path to a text file with one URL per line")
    parser.add_argument(
        "--audio-lang",
        type=str,
        default="ja-JP",
        help='Audio language(s), comma-separated (e.g. "ja-JP,en-US"), or "all" for every available dub. First is default.',
    )
    parser.add_argument(
        "--subs-lang",
        type=str,
        default="en-US",
        help='Subtitle language(s), comma-separated (e.g. "en-US,es-419"), or "all" for every available subtitle.',
    )
    parser.add_argument("--video-quality", type=str, default="1080p", help="Video quality (1080p, 720p, 480p, 360p)")
    parser.add_argument("--audio-quality", type=str, default="192k", help="Audio quality (192k, 96k)")
    parser.add_argument("--quality-video", type=str, default="", help="Alias for --video-quality")
    parser.add_argument("--quality-audio", type=str, default="", help="Alias for --audio-quality")
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Worker concurrency for downloading segments (default 8)",
    )
    parser.add_argument(
        "-x",
        "--server",
        type=int,
        default=1,
        help="CDN mirror/server index parsed from manifest (1 to N, default 1)",
    )
    parser.add_argument(
        "--disable-hedging",
        action="store_true",
        help="Disable tail-latency chunk hedging",
    )
    parser.add_argument(
        "--enable-hedging",
        action="store_true",
        help="Enable tail-latency chunk hedging (disabled by default)",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Season number to download (e.g. 1, 2, 4, 0). If omitted, downloads all seasons.",
    )
    parser.add_argument(
        "--list-seasons",
        "-ls",
        action="store_true",
        help="List all available seasons/arcs for the series and exit",
    )
    parser.add_argument(
        "--etp-rt",
        type=str,
        default="",
        help='The "etp_rt" cookie value of your account',
    )
    parser.add_argument(
        "--debug-manifest",
        action="store_true",
        help="Log raw episode playback JSON and manifest XML",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Redownload completed episodes and atomically replace existing MKV files",
    )
    parser.add_argument(
        "positional_url",
        nargs="?",
        default="",
        help="Optional URL of the episode/season/series to download (alternative to --url)",
    )

    args = parser.parse_args()
    if args.positional_url and not args.url:
        args.url = args.positional_url

    # launch gui if asked or if we have no inputs
    if args.gui or len(sys.argv) == 1 or (not args.url and not args.file and not args.etp_rt and not args.email):
        ensure_webview2()
        from web_gui import start_gui
        start_gui(port=8000, use_browser=args.browser)
        return

    from crunchyroll.auth import load_config, save_config

    etp_rt = ""
    if args.etp_rt:
        etp_rt = args.etp_rt
        save_config({"etp_rt": etp_rt})
    else:
        cfg = load_config()
        etp_rt = cfg.get("etp_rt", "")

    cfg = load_config()
    has_android_auth = bool(cfg.get("android_access_token")) or bool(args.email and args.password)

    if not etp_rt and not has_android_auth:
        print(
            "No active Crunchyroll session token found!\n"
            "1. Log in with Android TV credentials: python main.py --email USER --password PASS\n"
            "2. Or launch the Web GUI using: python main.py --gui\n"
            "3. Or pass your etp_rt token with --etp-rt \"TOKEN\""
        )
        sys.exit(1)

    client = CrunchyrollHttpClient(etp_rt=etp_rt or None, username=args.email or None, password=args.password or None)

    if args.list_seasons:
        if not args.url:
            print("Error: --url is required when using --list-seasons (e.g. --url https://www.crunchyroll.com/series/...)")
            sys.exit(1)

        from crunchyroll.api import get_seasons, parse_url_type
        kind, cid = parse_url_type(args.url)
        series_id = cid
        series_title = ""

        if kind == "episode":
            try:
                resp = client.do_request("GET", f"https://www.crunchyroll.com/content/v2/cms/objects/{cid}")
                if resp.status_code == 200:
                    items = resp.json().get("data", [])
                    if items:
                        meta = items[0].get("episode_metadata", {})
                        series_id = meta.get("series_id", cid)
                        series_title = meta.get("series_title", "")
            except Exception:
                pass
        elif kind == "series":
            try:
                resp = client.do_request("GET", f"https://www.crunchyroll.com/content/v2/cms/series/{cid}")
                if resp.status_code == 200:
                    items = resp.json().get("data", [])
                    if items:
                        series_title = items[0].get("title", "")
            except Exception:
                pass

        primary_audio = [x.strip() for x in args.audio_lang.split(",") if x.strip()][0] if args.audio_lang else "ja-JP"
        if primary_audio.lower() in ("all", "*"):
            primary_audio = "ja-JP"
        primary_subs = [x.strip() for x in args.subs_lang.split(",") if x.strip()][0] if args.subs_lang else "en-US"
        if primary_subs.lower() in ("all", "*"):
            primary_subs = "en-US"

        seasons = get_seasons(client, series_id, audio_locale=primary_audio, sub_locale=primary_subs)
        if not seasons:
            print(f"No seasons found for {args.url}")
            sys.exit(1)

        header = f"Seasons available for '{series_title}' ({series_id}):" if series_title else f"Seasons available for {series_id}:"
        print()
        print(header)
        print("=" * max(len(header), 60))
        for s in seasons:
            clean_title = s.title.strip()
            if series_title and clean_title.lower().startswith(series_title.lower()):
                clean_title = clean_title[len(series_title):].strip(" :-–—")
            if not clean_title:
                clean_title = f"Season {s.season_number}"
            elif s.season_number == 0 and "special" not in clean_title.lower() and "movie" not in clean_title.lower():
                clean_title = f"Specials • {clean_title}"

            print(f"  --season {s.season_number:<3} | {clean_title}")
        print("=" * max(len(header), 60))
        print("To download a season, run:")
        print(f"  python main.py --url {args.url} --season <number>")
        print()
        sys.exit(0)

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                urls = [
                    line.strip()
                    for line in f
                    if line.strip() and line.strip().startswith("http")
                ]
        except Exception as e:
            print(f"Failed to open URLs file: {e}")
            sys.exit(1)

        print(f"Found {len(urls)} URLs to download\n")
        for i, u in enumerate(urls):
            print(f"=== [{i+1}/{len(urls)}] {u} ===")
            process_url(client, u, args)
            print()
    else:
        process_url(client, args.url, args)


if __name__ == "__main__":
    main()
