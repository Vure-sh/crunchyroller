import http.server
import json
import logging
import os
import random
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Optional
from urllib.parse import parse_qs, urlparse

from crunchyroll import __version__
from crunchyroll.logger import get_default_log_dir, get_log_path, is_logging_enabled, set_logging_enabled, setup_logging
from crunchyroll.version import check_for_updates

# Ensure pywebview uses PyQt6 on Linux when available
os.environ.setdefault("QT_API", "pyqt6")

logger = logging.getLogger("crunchyroller.gui")

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

from crunchyroll.api import (
    get_episode_info,
    get_season_episodes,
    get_series,
    parse_url_type,
    purge_orphan_streams,
)
from crunchyroll.auth import load_config, save_config
from crunchyroll.downloader import download_episode
from crunchyroll.http_client import CrunchyrollHttpClient
from crunchyroll.queue import DownloadQueue
from crunchyroll.session_pool import ConcurrencyConfig
from crunchyroll.state_store import StateStore
from crunchyroll.types import DEFAULT_DOWNLOAD_DIR

# root folder for static web assets
base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(base_dir, "web")
if not os.path.exists(WEB_DIR):
    WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# global download & app state
CURRENT_WINDOW = None
initial_cfg = load_config()
STATE = {
    "etp_rt": initial_cfg.get("etp_rt", ""),
    "android_token": initial_cfg.get("android_access_token", ""),
    "config": {
        "video_quality": initial_cfg.get("video_quality", "1080p"),
        "audio_quality": initial_cfg.get("audio_quality", "192k"),
        "audio_lang":    initial_cfg.get("audio_lang", "ja-JP"),
        "subs_lang":     initial_cfg.get("subs_lang", "en-US"),
        "force_download": bool(initial_cfg.get("force_download", False)),
        "download_dir":  initial_cfg.get("download_dir", DEFAULT_DOWNLOAD_DIR),
        "workers":       max(1, min(32, int(initial_cfg.get("workers", 16)))),
        "enable_hedging": bool(initial_cfg.get("enable_hedging", False)),
        "enable_resume": bool(initial_cfg.get("enable_resume", True)),
        "enable_logging": bool(initial_cfg.get("enable_logging", True)),
        "bitrate_mode":  str(initial_cfg.get("bitrate_mode", "highest")),
        "enable_antiratelimit": bool(initial_cfg.get("enable_antiratelimit", False)),
        "antiratelimit_delay": max(5, min(180, int(initial_cfg.get("antiratelimit_delay", 60)))),
        "antiratelimit_jitter": max(2, min(15, int(initial_cfg.get("antiratelimit_jitter", 5)))),
        "antiratelimit_reduce_threads": bool(initial_cfg.get("antiratelimit_reduce_threads", True)),
        "audio_only_format": str(initial_cfg.get("audio_only_format", "mka")),
    },
    "download": {
        "status":      "idle",
        "episode":     "",
        "track":       "",
        "ep_idx":      0,
        "ep_total":    0,
        "segs_done":   0,
        "segs_total":  0,
        "speed":       "",
        "complete_file": False,
        "overall_pct": 0.0,
        "track_pct":   0.0,
        "log":         [],
        "queue":       [],
        "queued_count": 0,
    },
}
set_logging_enabled(STATE["config"]["enable_logging"])
LOCK = threading.RLock()
DOWNLOAD_PAUSE_EVENT = threading.Event()
DOWNLOAD_PAUSE_EVENT.set()
DOWNLOAD_CANCEL_EVENT = threading.Event()
DOWNLOAD_CANCEL_EVENT.clear()


def get_effective_cooldown() -> float:
    """Calculate random-jittered episode cooldown delay for anti-ratelimit protection."""
    with LOCK:
        cfg = STATE["config"]
        if cfg.get("enable_antiratelimit", False):
            base_delay = float(cfg.get("antiratelimit_delay", 60))
            jitter = float(cfg.get("antiratelimit_jitter", 5))
            variance = random.uniform(-jitter, jitter)
            return max(1.0, round(base_delay + variance, 2))
        return random.uniform(1.5, 3.0)


def get_effective_workers() -> int:
    """Return effective download worker threads, capping to 2 when anti-ratelimit safe mode is enabled."""
    with LOCK:
        cfg = STATE["config"]
        if cfg.get("enable_antiratelimit", False) and cfg.get("antiratelimit_reduce_threads", False):
            return 2
        return max(1, min(32, int(cfg.get("workers", 16))))


STATE_STORE = StateStore()

QUEUE = DownloadQueue(
    client_factory=lambda: CrunchyrollHttpClient(),
    pause_event=DOWNLOAD_PAUSE_EVENT,
    cancel_event=DOWNLOAD_CANCEL_EVENT,
    lock=LOCK,
    cooldown_range=(1.5, 3.0),
    cooldown_provider=get_effective_cooldown,
    state_store=STATE_STORE,
)


def get_auth_type() -> str:
    cfg = load_config()
    with LOCK:
        if STATE.get("android_token") or cfg.get("android_access_token") or cfg.get("android_refresh_token"):
            return "android_tv"
        if STATE.get("etp_rt") or cfg.get("etp_rt"):
            return "token"
    return "none"


def is_authenticated() -> bool:
    return get_auth_type() != "none"


def is_webview2_installed() -> bool:
    """check if WebView2 runtime is installed on Windows"""
    if sys.platform != "win32":
        return True
    try:
        import winreg
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
    except Exception:
        pass
    return False


def get_system_clipboard() -> str:
    """Safely retrieves text from the system clipboard across platforms."""
    # 1. Try Qt application instance if available
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            cb = app.clipboard()
            if cb:
                text = cb.text()
                if text:
                    return text
    except Exception:
        pass

    # 2. Try Windows ctypes
    if sys.platform == "win32":
        try:
            import ctypes
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    h_mem = user32.GetClipboardData(CF_UNICODETEXT)
                    if h_mem:
                        ptr = kernel32.GlobalLock(h_mem)
                        if ptr:
                            try:
                                val = ctypes.c_wchar_p(ptr).value
                                if val:
                                    return val
                            finally:
                                kernel32.GlobalUnlock(h_mem)
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass

    # 3. Try Linux wl-paste / xclip
    if sys.platform != "win32":
        for cmd in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"]):
            try:
                import subprocess
                out = subprocess.check_output(cmd, timeout=0.5, stderr=subprocess.DEVNULL)
                text = out.decode("utf-8", errors="replace")
                if text:
                    return text
            except Exception:
                pass

    return ""


def set_system_clipboard(text: str) -> bool:
    """Safely sets text into the system clipboard across platforms."""
    if not text:
        return True

    # 1. Try Qt application instance
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            cb = app.clipboard()
            if cb:
                cb.setText(text)
                return True
    except Exception:
        pass

    # 2. Try Windows ctypes
    if sys.platform == "win32":
        try:
            import ctypes
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    encoded = text.encode("utf-16le") + b"\x00\x00"
                    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                    if h_mem:
                        ptr = kernel32.GlobalLock(h_mem)
                        if ptr:
                            ctypes.memmove(ptr, encoded, len(encoded))
                            kernel32.GlobalUnlock(h_mem)
                            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                            return True
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass

    # 3. Try Linux wl-copy / xclip
    if sys.platform != "win32":
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
            try:
                import subprocess
                subprocess.run(cmd, input=text.encode("utf-8"), timeout=0.5, check=True)
                return True
            except Exception:
                pass

    return False


def open_path_in_file_manager(path: str) -> bool:
    """Safely opens a directory or file in the host operating system's native file manager."""
    if not path:
        return False
    target = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(target):
        if not os.path.splitext(target)[1]:
            try:
                os.makedirs(target, exist_ok=True)
            except Exception:
                pass
        else:
            parent = os.path.dirname(target)
            if not os.path.exists(parent):
                return False

    folder = target if os.path.isdir(target) else os.path.dirname(target)
    try:
        if sys.platform == "win32":
            if os.path.isfile(target):
                subprocess.Popen(["explorer", f"/select,{target}"])
            else:
                os.startfile(folder)
            return True
        elif sys.platform == "darwin":
            if os.path.isfile(target):
                subprocess.Popen(["open", "-R", target])
            else:
                subprocess.Popen(["open", folder])
            return True
        else:
            # Linux / FreeDesktop
            subprocess.Popen(["xdg-open", folder])
            return True
    except Exception as e:
        logger.error("Failed to open file manager for %s: %s", target, e)
        return False


def get_log_tail(lines: int = 150) -> str:
    """Safely reads the last N lines from crunchyroller.log."""
    log_file = get_log_path()
    if not os.path.exists(log_file):
        return ""
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading log file: {e}"


def _log(msg):
    logger.info("%s", msg)
    try:
        if "QUEUE" in globals() and QUEUE:
            QUEUE.log(msg)
    except Exception:
        pass
    with LOCK:
        STATE["download"]["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if len(STATE["download"]["log"]) > 200:
            STATE["download"]["log"].pop(0)


def _run_download(items, vq, aq, al, sl, force_download=False):
    DOWNLOAD_PAUSE_EVENT.set()
    DOWNLOAD_CANCEL_EVENT.clear()
    ep_total = len(items)
    with LOCK:
        STATE["download"].update(
            status="running", episode="", speed="", track="",
            segs_done=0, segs_total=0, ep_idx=0, ep_total=ep_total,
            overall_pct=0.0, track_pct=0.0, complete_file=False, log=[],
        )

    client = CrunchyrollHttpClient()
    _log(f"starting {ep_total} episode(s)...")

    a_langs = [x.strip() for x in al.split(",") if x.strip()] or ["ja-JP"]
    s_langs = [x.strip() for x in sl.split(",") if x.strip()] or ["en-US"]

    for idx, item in enumerate(items):
        if DOWNLOAD_CANCEL_EVENT.is_set():
            _log("download cancelled by user.")
            with LOCK:
                STATE["download"].update(status="canceled", speed="", track="canceled")
            return

        if not DOWNLOAD_PAUSE_EVENT.is_set():
            _log("download paused.")
            with LOCK:
                STATE["download"]["status"] = "paused"
                STATE["download"]["speed"] = "paused"
            while not DOWNLOAD_PAUSE_EVENT.is_set():
                if DOWNLOAD_CANCEL_EVENT.is_set():
                    _log("download cancelled by user.")
                    with LOCK:
                        STATE["download"].update(status="canceled", speed="", track="canceled")
                    return
                time.sleep(0.5)
            with LOCK:
                if STATE["download"]["status"] == "paused":
                    STATE["download"]["status"] = "running"
            _log("download resumed.")

        if idx > 0:
            time.sleep(random.uniform(1.5, 3.0))
        ep_id = item.get("id") if isinstance(item, dict) else item
        try:
            info = get_episode_info(client, ep_id)
            label = f"S{info.episode_metadata.season_number:02d}E{info.episode_metadata.episode_number:02d} \u2014 {info.title}"
            with LOCK:
                STATE["download"]["ep_idx"]      = idx
                STATE["download"]["episode"]     = label
                STATE["download"]["track"]       = "starting"
                STATE["download"]["segs_done"]   = 0
                STATE["download"]["segs_total"]  = 0
                STATE["download"]["track_pct"]   = 0.0
                STATE["download"]["overall_pct"] = round((idx / ep_total) * 100, 1)
            _log(f"[{idx+1}/{ep_total}] {label} [{vq}/{aq}]")

            def _cb(title, cur, tot, speed, status, _idx=idx):
                ep_base = (_idx / ep_total) * 100
                ep_slice = (1 / ep_total) * 100

                track_type = str(status).lower() if status else "video"
                frac = (cur / tot) if tot > 0 else 0.0
                complete_file = track_type.endswith("-file")
                if complete_file:
                    track_type = track_type[:-5]

                is_paused = track_type.endswith("-paused") or not DOWNLOAD_PAUSE_EVENT.is_set()
                if track_type.endswith("-paused"):
                    track_type = track_type[:-7]

                if "audio-only" in track_type:
                    within_ep = frac * 0.95
                    display_track = "audio"
                elif "audio" in track_type:
                    # Audio represents the first 15% of the episode
                    within_ep = frac * 0.15
                    display_track = "audio"
                elif "mux" in track_type:
                    within_ep = 0.98
                    display_track = "muxing"
                elif "done" in track_type:
                    within_ep = 1.0
                    display_track = "done"
                else:
                    # Video represents 15% - 95% of the episode
                    within_ep = 0.15 + (frac * 0.80)
                    display_track = "video"

                overall = round(ep_base + (within_ep * ep_slice), 1)
                cap = round(((_idx + 1) / ep_total) * 100 - 0.1, 1)

                with LOCK:
                    STATE["download"]["segs_done"]   = cur
                    STATE["download"]["segs_total"]  = tot
                    STATE["download"]["speed"]        = "paused" if is_paused else (speed or "")
                    STATE["download"]["track"]        = display_track
                    STATE["download"]["track_pct"]   = round(within_ep * 100.0, 1) if "mux" not in track_type else 98.0
                    STATE["download"]["overall_pct"] = min(overall, cap)
                    STATE["download"]["complete_file"] = complete_file
                    STATE["download"]["status"]      = "paused" if is_paused else "running"

            download_dir = STATE["config"].get("download_dir", DEFAULT_DOWNLOAD_DIR)
            workers_cnt = get_effective_workers()
            hedging = bool(STATE["config"].get("enable_hedging", False))
            resume = bool(STATE["config"].get("enable_resume", True))
            bitrate_mode = str(STATE["config"].get("bitrate_mode", "highest"))
            download_episode(
                client=client, base_content_id=ep_id, info=info,
                audio_langs=a_langs, subs_langs=s_langs,
                video_quality=vq, audio_quality=aq, progress_cb=_cb,
                force_download=force_download,
                pause_event=DOWNLOAD_PAUSE_EVENT,
                cancel_event=DOWNLOAD_CANCEL_EVENT,
                download_dir=download_dir,
                resume=resume,
                bitrate_mode=bitrate_mode,
                concurrency_config=ConcurrencyConfig(
                    min_workers=1 if workers_cnt <= 2 else max(2, workers_cnt // 2),
                    max_workers=workers_cnt,
                    initial_workers=workers_cnt,
                    pool_size=max(4, min(64, workers_cnt * 2)),
                    hedging_enabled=hedging,
                ),
            )
            with LOCK:
                STATE["download"]["overall_pct"] = round(((idx + 1) / ep_total) * 100, 1)
                STATE["download"]["track_pct"]   = 100.0
                STATE["download"]["track"]       = "done"
                STATE["download"]["speed"]       = ""
            _log(f"done: {label}")

        except Exception as e:
            if DOWNLOAD_CANCEL_EVENT.is_set() or isinstance(e, InterruptedError):
                _log(f"canceled by user: {label}")
                with LOCK:
                    STATE["download"].update(status="canceled", episode=f"canceled: {label}", speed="", track="canceled")
                return
            _log(f"error on {ep_id}: {e}")
            logger.error("Download failed for %s: %s", ep_id, e, exc_info=True)
            with LOCK:
                STATE["download"].update(status="error", episode=f"failed: {ep_id}")
            return

    with LOCK:
        if not DOWNLOAD_CANCEL_EVENT.is_set():
            STATE["download"].update(
                status="completed", overall_pct=100.0, track_pct=100.0,
                episode="all done", track="", speed=""
            )
    _log(f"finished {ep_total} episode(s)")




# http request handler
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _get_cors_origin(self) -> Optional[str]:
        origin = self.headers.get("Origin")
        if not origin:
            return None
        parsed = urlparse(origin)
        if parsed.hostname in ("127.0.0.1", "localhost", "::1") or origin == "null":
            return origin
        return None

    def _validate_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            return parsed.hostname in ("127.0.0.1", "localhost", "::1") or origin == "null"
        referer = self.headers.get("Referer")
        if referer:
            parsed = urlparse(referer)
            return parsed.hostname in ("127.0.0.1", "localhost", "::1")
        return True

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        cors_origin = self._get_cors_origin()
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        cors_origin = self._get_cors_origin()
        if cors_origin:
            self.send_response(204)
            for h, v in [
                ("Access-Control-Allow-Origin", cors_origin),
                ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type"),
            ]:
                self.send_header(h, v)
            self.end_headers()
        else:
            self.send_response(403)
            self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # Defense in depth: even read-only API routes require a valid origin.
        # State-changing actions are POST-only (see below); plain <img>/link
        # navigations from foreign sites must never reach API logic.
        if path.startswith("/api/") and not self._validate_origin():
            self._json({"success": False, "error": "Forbidden: invalid origin"}, 403)
            return

        if path == "/api/state":
            auth_type = get_auth_type()
            with LOCK:
                q_state = QUEUE.get_state()
                if QUEUE.active_job or len(QUEUE.queue) > 0 or QUEUE.completed_batch_count > 0:
                    STATE["download"].update({
                        "status": q_state["status"],
                        "episode": q_state["episode"],
                        "track": q_state["track"],
                        "segs_done": q_state["segs_done"],
                        "segs_total": q_state["segs_total"],
                        "speed": q_state["speed"],
                        "overall_pct": q_state["overall_pct"],
                        "track_pct": q_state["track_pct"],
                        "ep_idx": q_state["ep_idx"],
                        "ep_total": q_state["ep_total"],
                        "complete_file": q_state["complete_file"],
                    })
                STATE["download"]["queue"] = q_state["queue"]
                STATE["download"]["queued_count"] = q_state["queued_count"]
                STATE["download"]["active_job"] = q_state["active_job"]
                STATE["download"]["history"] = q_state["history"]
                STATE["download"]["tasks"] = q_state.get("tasks", [])
                STATE["download"]["log"] = q_state.get("log", [])

                # Keep STATE in sync with config.json on disk so manual user edits are immediately honored
                disk_cfg = load_config()
                for k in ("video_quality", "audio_quality", "audio_lang", "subs_lang", "force_download", "workers", "enable_hedging", "enable_resume", "enable_logging", "bitrate_mode"):
                    if k in disk_cfg:
                        if k == "workers":
                            try:
                                STATE["config"][k] = max(4, min(32, int(disk_cfg[k])))
                            except (TypeError, ValueError):
                                STATE["config"][k] = 16
                        elif k in ("enable_hedging", "enable_resume", "force_download", "enable_logging"):
                            STATE["config"][k] = bool(disk_cfg[k])
                        else:
                            STATE["config"][k] = disk_cfg[k]
                STATE["config"]["download_dir"] = disk_cfg.get("download_dir", DEFAULT_DOWNLOAD_DIR)
                if disk_cfg.get("etp_rt"):
                    STATE["etp_rt"] = disk_cfg["etp_rt"]
                if disk_cfg.get("android_access_token"):
                    STATE["android_token"] = disk_cfg["android_access_token"]

                self._json({
                    "authenticated": auth_type != "none",
                    "auth_type": auth_type,
                    "config": STATE["config"],
                    "download": STATE["download"],
                    "queue": q_state["queue"],
                    "tasks": q_state.get("tasks", []),
                    "log_path": get_log_path(),
                    "version": __version__,
                })
            return

        elif path == "/api/queue":
            self._json({
                "success": True,
                "queue": QUEUE.get_queue_list(),
                "active": QUEUE.get_active_job(),
                "tasks": QUEUE.get_tasks_list(),
            })
            return

        elif path == "/api/queue/history":
            self._json({
                "success": True,
                "history": QUEUE.get_history_list(),
            })
            return

        elif path == "/api/partials/status":
            with LOCK:
                dl_dir = STATE["config"].get("download_dir") or DEFAULT_DOWNLOAD_DIR
            dl_dir = os.path.abspath(os.path.expanduser(dl_dir))

            partials_roots = [
                os.path.join(dl_dir, ".cr_partials"),
                os.path.join(os.path.abspath(DEFAULT_DOWNLOAD_DIR), ".cr_partials"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cr_partials"),
            ]
            seen_roots = set()
            total_bytes = 0
            episodes = []

            for root_dir in partials_roots:
                if root_dir in seen_roots or not os.path.exists(root_dir) or not os.path.isdir(root_dir):
                    continue
                seen_roots.add(root_dir)
                try:
                    for ep_entry in os.scandir(root_dir):
                        if ep_entry.is_dir():
                            ep_id = ep_entry.name
                            ep_bytes = 0
                            file_count = 0
                            for item in os.scandir(ep_entry.path):
                                if item.is_file():
                                    try:
                                        sz = item.stat().st_size
                                        ep_bytes += sz
                                        file_count += 1
                                    except OSError:
                                        pass
                            if file_count > 0:
                                total_bytes += ep_bytes
                                episodes.append({
                                    "ep_id": ep_id,
                                    "bytes": ep_bytes,
                                    "size_mb": round(ep_bytes / (1024 * 1024), 2),
                                    "files": file_count,
                                    "path": ep_entry.path,
                                })
                except OSError:
                    pass

            self._json({
                "success": True,
                "total_bytes": total_bytes,
                "size_mb": round(total_bytes / (1024 * 1024), 2),
                "episodes_count": len(episodes),
                "episodes": episodes,
            })
            return

        elif path == "/api/clipboard/paste":
            self._json({"success": True, "text": get_system_clipboard()})
            return

        elif path == "/api/logs/open-folder":
            log_dir = get_default_log_dir()
            opened = open_path_in_file_manager(log_dir)
            self._json({"success": opened, "path": log_dir})
            return

        elif path == "/api/downloads/open-folder":
            query = parse_qs(parsed_url.query)
            target = query.get("path", [""])[0].strip()
            if not target:
                with LOCK:
                    target = STATE["config"].get("download_dir") or DEFAULT_DOWNLOAD_DIR
            target = os.path.abspath(os.path.expanduser(target))
            opened = open_path_in_file_manager(target)
            self._json({"success": opened, "path": target})
            return

        elif path == "/api/logs/content":
            log_path = get_log_path()
            tail = get_log_tail()
            self._json({
                "success": True,
                "path": log_path,
                "content": tail,
            })
            return

        elif path == "/api/version/check":
            query = parse_qs(parsed_url.query)
            force = query.get("force", ["0"])[0] in ("1", "true", "True")
            update_info = check_for_updates(force=force)
            self._json({"success": True, **update_info})
            return

        elif path in (
            "/api/download/pause",
            "/api/download/resume",
            "/api/download/skip",
            "/api/download/cancel",
            "/api/download/cancel-current",
            "/api/download/cancel-all",
            "/api/queue/remove",
            "/api/queue/clear",
            "/api/queue/history/clear",
            "/api/queue/resume-interrupted",
            "/api/queue/retry-failed",
            "/api/task/remove",
            "/api/task/cancel",
            "/api/tasks/clear",
            "/api/tasks/clear-finished",
            "/api/sessions/purge",
            "/api/partials/clean",
            "/api/clipboard/copy",
        ):
            # State-changing actions are POST-only. A plain GET (e.g. an
            # <img> tag on a foreign site) must never mutate download state.
            self._json(
                {"success": False, "error": f"{path} requires POST"},
                status=405,
            )
            return

        elif path.startswith("/api/"):
            self._json({"success": False, "error": f"Endpoint not found: {path}"}, 404)
            return

        # serve static files from web/ directory
        if path == "/":
            rel_path = "index.html"
        else:
            rel_path = path.lstrip("/")

        full_path = os.path.normpath(os.path.join(WEB_DIR, rel_path))

        # prevent directory traversal
        if not full_path.startswith(WEB_DIR) or not os.path.exists(full_path) or os.path.isdir(full_path):
            self.send_error(404, "File not found")
            return

        # content types
        ext = os.path.splitext(full_path)[1].lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        ctype = content_types.get(ext, "application/octet-stream")

        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(500, "Internal server error")

    def do_POST(self):
        if not self._validate_origin():
            self._json({"success": False, "error": "Forbidden: invalid origin"}, 403)
            return

        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw)
        except Exception:
            data = {}

        if path == "/api/login":
            tok = data.get("etp_rt", "").strip()
            if not tok:
                self._json({"success": False, "error": "paste your etp_rt token"}, 400); return
            try:
                CrunchyrollHttpClient(etp_rt=tok)
                with LOCK: STATE["etp_rt"] = tok
                save_config({"etp_rt": tok})
                self._json({"success": True})
            except Exception as e:
                self._json({"success": False, "error": str(e)}, 401)

        elif path == "/api/login-credentials":
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            if not username or not password:
                self._json({"success": False, "error": "Username and password required"}, 400)
                return
            try:
                from crunchyroll.auth import login_with_android_tv
                acc_tok, ref_tok = login_with_android_tv(username, password)
                with LOCK:
                    STATE["android_token"] = acc_tok
                save_config({
                    "android_access_token": acc_tok,
                    "android_refresh_token": ref_tok,
                    "username": username,
                })
                self._json({"success": True, "message": "Logged in successfully!"})
            except Exception as e:
                self._json({"success": False, "error": str(e)}, 401)

        elif path == "/api/config":
            with LOCK:
                disk_cfg = load_config()
                for k in ("video_quality", "audio_quality", "audio_lang", "subs_lang", "force_download", "download_dir", "workers", "enable_hedging", "enable_resume", "enable_logging", "bitrate_mode", "enable_antiratelimit", "antiratelimit_delay", "antiratelimit_jitter", "antiratelimit_reduce_threads", "audio_only_format"):
                    if k in data:
                        val = data[k]
                        if k == "download_dir":
                            val = str(val).strip() if val is not None else ""
                            if not val or val == DEFAULT_DOWNLOAD_DIR:
                                val = DEFAULT_DOWNLOAD_DIR
                            else:
                                val = os.path.abspath(os.path.expanduser(val))
                        elif k == "workers":
                            try:
                                val = max(1, min(32, int(val)))
                            except (TypeError, ValueError):
                                val = 16
                        elif k == "antiratelimit_delay":
                            try:
                                val = max(5, min(180, int(val)))
                            except (TypeError, ValueError):
                                val = 60
                        elif k == "antiratelimit_jitter":
                            try:
                                val = max(2, min(15, int(val)))
                            except (TypeError, ValueError):
                                val = 5
                        elif k in ("enable_hedging", "enable_resume", "force_download", "enable_logging", "enable_antiratelimit", "antiratelimit_reduce_threads"):
                            val = bool(val)
                        elif k == "audio_only_format":
                            val = str(val or "mka").lower().strip()
                            if val not in ("mka", "mkv", "standalone"):
                                val = "mka"
                        STATE["config"][k] = val
                        disk_cfg[k] = val
                        if k == "enable_logging":
                            set_logging_enabled(val)
            save_config(disk_cfg)
            self._json({
                "success": True,
                "config": STATE["config"],
                "download_dir": STATE["config"].get("download_dir", DEFAULT_DOWNLOAD_DIR),
            })

        elif path in ("/api/choose-directory", "/api/browse-directory"):
            chosen = None
            # 1. If running inside pywebview window, use its native folder picker
            if CURRENT_WINDOW is not None:
                try:
                    import webview
                    dialog_type = getattr(webview.FileDialog, "FOLDER", None) if hasattr(webview, "FileDialog") else getattr(webview, "FOLDER_DIALOG", None)
                    res = CURRENT_WINDOW.create_file_dialog(dialog_type)
                    if res and len(res) > 0:
                        chosen = res[0]
                except Exception as e:
                    print(f"[gui] folder dialog error: {e}")

            # 2. Fallback to tkinter if pywebview didn't return or browser mode
            if not chosen:
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes("-topmost", True)
                    chosen = filedialog.askdirectory(title="Select Download Directory")
                    root.destroy()
                except Exception:
                    chosen = None

            if chosen:
                chosen = os.path.abspath(os.path.expanduser(chosen))
                with LOCK:
                    STATE["config"]["download_dir"] = chosen
                    disk_cfg = load_config()
                    disk_cfg["download_dir"] = chosen
                    save_config(disk_cfg)
                self._json({"success": True, "download_dir": chosen})
            else:
                self._json({"success": False, "error": "No directory selected", "cancelled": True})
            return

        elif path == "/api/fetch":
            url = data.get("url","").strip()
            if not url: self._json({"success":False,"error":"url required"},400); return
            if not is_authenticated():
                self._json({"success":False,"error":"not logged in"},401); return
            try:
                client = CrunchyrollHttpClient()
                kind, cid = parse_url_type(url)
                al, sl = STATE["config"].get("audio_lang", "ja-JP"), STATE["config"].get("subs_lang", "en-US")
                al_list = [x.strip() for x in al.split(",") if x.strip()]
                sl_list = [x.strip() for x in sl.split(",") if x.strip()]
                primary_al = al_list[0] if al_list else "ja-JP"
                primary_sl = sl_list[0] if sl_list else "en-US"
                api_audio = primary_al if primary_al.lower() not in {"all", "*"} else "ja-JP"
                api_subs = primary_sl if primary_sl.lower() not in {"all", "*"} else "en-US"
                avail_audios = []
                if kind == "episode":
                    info = get_episode_info(client, cid)
                    seasons = [{
                        "season_number": info.episode_metadata.season_number,
                        "title": getattr(info.episode_metadata, "season_title", "") or f"Season {info.episode_metadata.season_number}",
                        "episodes": [{
                            "id": cid,
                            "title": info.title,
                            "episode_number": info.episode_metadata.episode_number,
                            "season_number": info.episode_metadata.season_number,
                            "series_title": info.episode_metadata.series_title,
                            "season_title": getattr(info.episode_metadata, "season_title", ""),
                        }],
                    }]
                    title = info.episode_metadata.series_title
                    avail_audios = [v.audio_locale for v in info.episode_metadata.versions if v.audio_locale]
                else:
                    s = get_series(client, cid, api_audio, api_subs)
                    title = s.get("title", "")
                    seasons = []
                    seen_season_ids = set()

                    for sn in s.get("seasons", []):
                        if sn.id in seen_season_ids:
                            continue
                        seen_season_ids.add(sn.id)

                        eps = [
                            e for e in s.get("episodes", [])
                            if getattr(e, "season_id", "") == sn.id
                            or (not getattr(e, "season_id", "") and e.season_number == sn.season_number)
                        ]
                        if not eps:
                            continue

                        seasons.append({
                            "id": sn.id,
                            "season_number": sn.season_number,
                            "title": sn.title or f"Season {sn.season_number}",
                            "audio_locale": sn.audio_locale,
                            "episodes": [
                                {
                                    "id": e.id,
                                    "title": e.title,
                                    "episode_number": e.episode_number,
                                    "season_number": e.season_number,
                                    "series_title": e.series_title,
                                    "season_title": getattr(e, "season_title", "") or sn.title or "",
                                }
                                for e in eps
                            ],
                        })
                        if getattr(sn, "audio_locale", None) and sn.audio_locale not in avail_audios:
                            avail_audios.append(sn.audio_locale)
                self._json({"success":True,"title":title,"seasons":seasons,"avail_audios":avail_audios})
            except Exception as e:
                self._json({"success":False,"error":str(e)},500)

        elif path == "/api/download":
            if not is_authenticated():
                self._json({"success": False, "error": "not logged in"}, 401)
                return
            items = data.get("items", [])
            if not items:
                self._json({"success": False, "error": "select some episodes"}, 400)
                return
            c = STATE["config"]
            vq = data.get("video_quality", c["video_quality"])
            aq = data.get("audio_quality", c["audio_quality"])
            al = data.get("audio_lang", c["audio_lang"])
            sl = data.get("subs_lang", c["subs_lang"])
            fd = bool(data.get("force_download", c.get("force_download", False)))
            if c.get("enable_antiratelimit") and c.get("antiratelimit_reduce_threads"):
                workers = 2
            else:
                workers = int(data.get("workers", c.get("workers", 16)))
            enable_hedging = bool(data.get("enable_hedging", c.get("enable_hedging", False)))
            enable_resume = bool(data.get("enable_resume", c.get("enable_resume", True)))
            bitrate_mode = str(data.get("bitrate_mode") or c.get("bitrate_mode") or "highest").strip()

            dl_dir = str(data.get("download_dir") or c.get("download_dir") or DEFAULT_DOWNLOAD_DIR).strip() or DEFAULT_DOWNLOAD_DIR
            task_title = str(data.get("task_title") or data.get("series_title") or "").strip()
            enqueued = QUEUE.enqueue_batch(items, {
                "video_quality": vq,
                "audio_quality": aq,
                "audio_lang": al,
                "subs_lang": sl,
                "force_download": fd,
                "download_dir": dl_dir,
                "workers": workers,
                "enable_hedging": enable_hedging,
                "enable_resume": enable_resume,
                "bitrate_mode": bitrate_mode,
            }, task_title=task_title)
            with LOCK:
                STATE["download"]["status"] = "running"
            self._json({
                "success": True,
                "enqueued_count": len(enqueued),
                "queued_total": QUEUE.queued_count,
                "message": f"Added {len(enqueued)} episode(s) to queue",
            })

        elif path == "/api/download/pause":
            QUEUE.pause()
            DOWNLOAD_PAUSE_EVENT.clear()
            with LOCK:
                if STATE["download"]["status"] == "running":
                    STATE["download"]["status"] = "paused"
                    STATE["download"]["speed"] = "paused"
            _log("download paused by user")
            self._json({"success": True, "status": "paused"})

        elif path == "/api/download/resume":
            QUEUE.resume()
            DOWNLOAD_PAUSE_EVENT.set()
            with LOCK:
                if STATE["download"]["status"] == "paused":
                    STATE["download"]["status"] = "running"
            _log("download resumed by user")
            self._json({"success": True, "status": "running"})

        elif path == "/api/download/skip":
            job_id = str(data.get("id") or data.get("job_id") or "").strip() or None
            QUEUE.cancel_current(job_id=job_id)
            _log("active episode skipped by user")
            self._json({"success": True, "status": "skipped"})

        elif path == "/api/download/cancel-current":
            job_id = str(data.get("id") or data.get("job_id") or "").strip() or None
            QUEUE.cancel_current(job_id=job_id)
            DOWNLOAD_CANCEL_EVENT.set()
            DOWNLOAD_PAUSE_EVENT.set()
            with LOCK:
                if QUEUE.queued_count == 0 and not QUEUE.active_job:
                    STATE["download"]["status"] = "canceled"
                STATE["download"]["speed"] = ""
            _log("active episode cancelled by user")
            self._json({"success": True, "status": "canceled"})

        elif path in ("/api/download/cancel", "/api/download/cancel-all"):
            if data.get("current_only"):
                job_id = str(data.get("id") or data.get("job_id") or "").strip() or None
                QUEUE.cancel_current(job_id=job_id)
                DOWNLOAD_CANCEL_EVENT.set()
                DOWNLOAD_PAUSE_EVENT.set()
                with LOCK:
                    if QUEUE.queued_count == 0 and not QUEUE.active_job:
                        STATE["download"]["status"] = "canceled"
                    STATE["download"]["speed"] = ""
                _log("active episode cancelled by user")
                self._json({"success": True, "status": "canceled"})
            else:
                QUEUE.cancel_all()
                DOWNLOAD_CANCEL_EVENT.set()
                DOWNLOAD_PAUSE_EVENT.set()
                with LOCK:
                    STATE["download"]["status"] = "canceled"
                    STATE["download"]["speed"] = ""
                _log("all downloads cancelled by user")
                self._json({"success": True, "status": "canceled"})

        elif path == "/api/queue/remove":
            job_id = str(data.get("id", "")).strip()
            removed = QUEUE.remove(job_id)
            self._json({"success": removed})

        elif path == "/api/task/remove" or path == "/api/task/cancel":
            task_id = str(data.get("id") or data.get("task_id") or "").strip()
            removed = QUEUE.remove_task(task_id)
            self._json({"success": removed})

        elif path == "/api/tasks/clear" or path == "/api/tasks/clear-finished":
            include_active = bool(data.get("all") or data.get("include_active"))
            cleared = QUEUE.clear_tasks(include_active=include_active)
            self._json({"success": True, "cleared": cleared})

        elif path == "/api/queue/clear":
            cleared = QUEUE.clear()
            self._json({"success": True, "cleared": cleared})

        elif path == "/api/queue/history/clear":
            cleared = QUEUE.clear_history()
            self._json({"success": True, "cleared": cleared})

        elif path == "/api/queue/resume-interrupted":
            resumed = QUEUE.resume_interrupted()
            self._json({"success": True, "resumed": resumed})

        elif path == "/api/queue/retry-failed":
            retried = QUEUE.retry_failed()
            self._json({"success": True, "retried": retried})

        elif path == "/api/sessions/purge":
            try:
                client = CrunchyrollHttpClient()
                purged = purge_orphan_streams(client, all_devices=True)
                _log(f"purged {purged} zombie session(s)")
                self._json({"success": True, "purged": purged})
            except Exception as e:
                self._json({"success": False, "error": str(e)}, status=500)

        elif path == "/api/partials/clean":
            with LOCK:
                dl_dir = STATE["config"].get("download_dir") or DEFAULT_DOWNLOAD_DIR
                active_job = QUEUE.active_job
                active_ep_id = active_job.ep_id if active_job else None

            dl_dir = os.path.abspath(os.path.expanduser(dl_dir))
            partials_roots = [
                os.path.join(dl_dir, ".cr_partials"),
                os.path.join(os.path.abspath(DEFAULT_DOWNLOAD_DIR), ".cr_partials"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cr_partials"),
            ]
            seen_roots = set()
            freed_bytes = 0
            cleaned_count = 0
            skipped_active = False

            import shutil
            for root_dir in partials_roots:
                if root_dir in seen_roots or not os.path.exists(root_dir) or not os.path.isdir(root_dir):
                    continue
                seen_roots.add(root_dir)
                try:
                    for ep_entry in os.scandir(root_dir):
                        if ep_entry.is_dir():
                            ep_id = ep_entry.name
                            if active_ep_id and ep_id == active_ep_id:
                                skipped_active = True
                                continue
                            ep_bytes = 0
                            for item in os.scandir(ep_entry.path):
                                if item.is_file():
                                    try:
                                        ep_bytes += item.stat().st_size
                                    except OSError:
                                        pass
                            try:
                                shutil.rmtree(ep_entry.path)
                                freed_bytes += ep_bytes
                                cleaned_count += 1
                            except OSError as err:
                                print(f"[partials] could not delete {ep_entry.path}: {err}")
                except OSError:
                    pass

            _log(f"Cleaned partial cache: freed {round(freed_bytes / (1024 * 1024), 2)} MB ({cleaned_count} episodes)")
            self._json({
                "success": True,
                "freed_bytes": freed_bytes,
                "freed_mb": round(freed_bytes / (1024 * 1024), 2),
                "cleaned_count": cleaned_count,
                "skipped_active": skipped_active,
            })

        elif path == "/api/clipboard/paste":
            self._json({"success": True, "text": get_system_clipboard()})

        elif path == "/api/clipboard/copy":
            text = str(data.get("text", ""))
            ok = set_system_clipboard(text)
            self._json({"success": ok})

        elif path == "/api/logs/open-folder":
            log_dir = get_default_log_dir()
            opened = open_path_in_file_manager(log_dir)
            self._json({"success": opened, "path": log_dir})

        elif path == "/api/downloads/open-folder":
            target = str(data.get("path") or "").strip()
            if not target:
                with LOCK:
                    target = STATE["config"].get("download_dir") or DEFAULT_DOWNLOAD_DIR
            target = os.path.abspath(os.path.expanduser(target))
            opened = open_path_in_file_manager(target)
            self._json({"success": opened, "path": target})

        elif path == "/api/logs/content":
            log_path = get_log_path()
            tail = get_log_tail()
            self._json({
                "success": True,
                "path": log_path,
                "content": tail,
            })

        elif path == "/api/version/check":
            force = bool(data.get("force", False))
            update_info = check_for_updates(force=force)
            self._json({"success": True, **update_info})

        elif path.startswith("/api/"):
            self._json({"success": False, "error": f"Endpoint not found: {path}. If you recently updated, please restart web_gui.py."}, 404)
        else:
            self.send_error(404)


def unblock_bundled_files() -> int:
    """Remove the Windows 'downloaded from the internet' flag (Zone.Identifier) from the
    bundled binaries and return how many were unblocked.

    A zip downloaded in a browser and extracted with Explorer tags every extracted file
    with this NTFS stream. .NET then refuses to load Python.Runtime.dll, and clr-loader
    swallows the real error and only reports 'Failed to resolve
    Python.Runtime.Loader.Initialize', which breaks the native window.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return 0

    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    unblocked = 0
    try:
        for root, _dirs, files in os.walk(app_dir):
            for name in files:
                if not name.lower().endswith((".dll", ".exe", ".pyd")):
                    continue
                stream = os.path.join(root, name) + ":Zone.Identifier"
                try:
                    os.remove(stream)
                    unblocked += 1
                except OSError:
                    # no stream on this file (the common case) or it is locked
                    pass
    except Exception as e:
        logger.warning("Could not unblock bundled files: %s", e)
        return unblocked

    if unblocked:
        logger.info("Removed internet-download flag from %d bundled file(s)", unblocked)
    return unblocked


def start_gui(port=8000, use_browser=False):
    """launch crunchyroller inside a native desktop pywebview window (or default browser)"""
    setup_logging()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server_thread = threading.Thread(target=srv.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"
    print(f"crunchyroller running on {url}")

    if use_browser:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nstopped.")
    else:
        try:
            # must run before pywebview imports clr, which loads Python.Runtime.dll
            unblock_bundled_files()
            import webview
            global CURRENT_WINDOW
            CURRENT_WINDOW = webview.create_window(
                "crunchyroller",
                url=url,
                width=860,
                height=760,
                min_size=(640, 520),
                background_color="#000000",
                text_select=True,
            )
            gui_backend = "qt" if sys.platform != "win32" else None
            if sys.platform != "win32":
                # Patch upstream pywebview PyQt6 bug where setFeaturePermission passes int instead of enum
                try:
                    from PyQt6.QtWebEngineCore import QWebEnginePage
                    _orig_perm = QWebEnginePage.setFeaturePermission

                    def _safe_perm(self, url, feature, policy):
                        cb_feature = getattr(QWebEnginePage.Feature, 'ClipboardReadWrite', None)
                        if cb_feature is not None and feature == cb_feature:
                            policy = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                        elif isinstance(policy, int):
                            if policy == 1:
                                policy = QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                            else:
                                policy = QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
                        return _orig_perm(self, url, feature, policy)

                    QWebEnginePage.setFeaturePermission = _safe_perm
                except Exception:
                    pass
            webview.start(gui=gui_backend)
        except Exception as e:
            logger.error("Native window launch failed: %s", e, exc_info=True)
            # only warn if webview2 is actually missing
            if sys.platform == "win32" and not is_webview2_installed():
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        "The app needs Microsoft Edge WebView2 to run as a native window.\n\n"
                        "Download it from:\nhttps://developer.microsoft.com/microsoft-edge/webview2/\n\n"
                        "Opening in your browser for now as a fallback.",
                        "WebView2 Required",
                        0x40  # MB_ICONINFORMATION
                    )
                except Exception:
                    pass
            print(f"native window failed ({e}), opening in browser...")
            webbrowser.open(url)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nstopped.")


