import json
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("crunchyroll.watcher")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONITORED_FILE = os.path.join(_PROJECT_ROOT, "monitored_series.json")
WATCHER_LOCK = threading.RLock()

DEFAULT_WATCHER_SETTINGS = {
    "enabled": True,
    "interval_minutes": 60,
    "default_mode": "latest_only",  # "latest_only" | "all_missing"
    "last_check_time": "",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()



def _episode_audio_locales(ep: Any) -> set:
    """Collect the audio locales an episode is available in (best effort)."""

    def _field(obj: Any, key: str) -> str:
        val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, "")
        return val if isinstance(val, str) else ""

    locales = set()
    base = _field(ep, "audio_locale").strip().lower()
    if base:
        locales.add(base)
    versions = ep.get("versions") if isinstance(ep, dict) else getattr(ep, "versions", None)
    if isinstance(versions, (list, tuple)):
        for v in versions:
            loc = _field(v, "audio_locale").strip().lower()
            if loc:
                locales.add(loc)
    return locales


def _audio_ready(client: Any, ep: Any, ep_id: str, audio_langs: List[str], audio_fallback: bool) -> bool:
    """Return whether an episode can be downloaded in the requested audio right now.

    With audio fallback enabled, or when every track is requested, any episode
    counts as ready (the existing behavior). Otherwise the episode only counts
    once its dub versions cover at least one requested language - the exact
    condition under which the downloader would NOT skip it - so an episode that
    only aired in the original audio stays pending until its dub is released.
    """
    if audio_fallback:
        return True
    wanted = [str(lang).strip().lower() for lang in audio_langs if str(lang).strip()]
    if not wanted or any(lang in ("all", "*") for lang in wanted):
        return True
    versions = ep.get("versions") if isinstance(ep, dict) else getattr(ep, "versions", None)
    has_versions = isinstance(versions, (list, tuple)) and len(versions) > 0
    if not has_versions:
        # The season listing carried no dub versions; ask the object endpoint.
        # The base audio_locale alone cannot be trusted here - it would hide
        # dubs that only the detailed metadata knows about.
        if client is None or not ep_id:
            return True  # nothing to verify with; never hit on live paths
        try:
            from crunchyroll.api import get_episode_info
            info = get_episode_info(client, ep_id)
            ep = info.episode_metadata
        except Exception as e:
            # Keep the episode pending and retry next pass. Returning ready
            # here would mark an unverified episode as known and lose it.
            logger.info("Could not verify audio versions for episode %s (%s); leaving it pending", ep_id, e)
            return False
    locales = _episode_audio_locales(ep)
    if not locales:
        # Even the detailed metadata carried no usable audio info, so the
        # episode is unverified - keep it pending and retry next pass rather
        # than marking it known.
        return False
    return any(lang in locales for lang in wanted)


class MonitoredStore:
    """Thread-safe persistent storage for monitored series and auto-downloader events."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or MONITORED_FILE
        self._lock = threading.RLock()

    def load(self) -> Dict[str, Any]:
        with self._lock:
            if not os.path.exists(self.file_path):
                data = {
                    "settings": dict(DEFAULT_WATCHER_SETTINGS),
                    "series": {},
                    "events": [],
                }
                self.save(data)
                return data

            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    return {"settings": dict(DEFAULT_WATCHER_SETTINGS), "series": {}, "events": []}
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    parsed = {}
                settings = dict(DEFAULT_WATCHER_SETTINGS)
                settings.update(parsed.get("settings", {}))
                return {
                    "settings": settings,
                    "series": parsed.get("series", {}) if isinstance(parsed.get("series"), dict) else {},
                    "events": parsed.get("events", []) if isinstance(parsed.get("events"), list) else [],
                }
            except Exception as e:
                logger.warning("Error reading %s: %s; using safe defaults", self.file_path, e)
                return {"settings": dict(DEFAULT_WATCHER_SETTINGS), "series": {}, "events": []}

    def save(self, data: Dict[str, Any]) -> None:
        with self._lock:
            dir_name = os.path.dirname(os.path.abspath(self.file_path)) or "."
            base_name = os.path.basename(self.file_path)
            temp_path = os.path.join(dir_name, f".{base_name}.tmp.{os.getpid()}")
            try:
                with open(temp_path, "w", encoding="utf-8", newline="\r\n") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, self.file_path)
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                logger.error("Failed writing %s: %s", self.file_path, e)


class SeriesWatcher:
    """Background engine monitoring ongoing anime series and queuing new episodes."""

    def __init__(
        self,
        queue: Any,
        client_factory: Callable[[], Any],
        config_provider: Callable[[], Dict[str, Any]],
        store: Optional[MonitoredStore] = None,
    ):
        self.queue = queue
        self.client_factory = client_factory
        self.config_provider = config_provider
        self.store = store or MonitoredStore()

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._is_checking = False
        self._last_check_start: Optional[float] = None
        self._unread_notifications: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="SeriesWatcherThread",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("Series Watcher background engine started.")

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            self._wake_event.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=3.0)
            self._worker_thread = None
            logger.info("Series Watcher background engine stopped.")

    def _worker_loop(self) -> None:
        # Give the main server 5 seconds to finish boot sequence before first check
        time.sleep(5)

        while not self._stop_event.is_set():
            data = self.store.load()
            settings = data.get("settings", {})
            enabled = bool(settings.get("enabled", True))
            interval_mins = max(0.5, float(settings.get("interval_minutes", 60)))
            interval_sec = interval_mins * 60.0

            if enabled:
                try:
                    self.check_all()
                except Exception as e:
                    logger.error("Watcher check error in loop: %s", e, exc_info=True)

            # Wait for interval or wake_event
            woken = self._wake_event.wait(timeout=interval_sec)
            if woken:
                self._wake_event.clear()

    def check_now(self) -> None:
        """Trigger an immediate asynchronous check cycle."""
        self._wake_event.set()

    def get_status(self) -> Dict[str, Any]:
        """Return real-time watcher status for API and frontend display."""
        with self._lock:
            data = self.store.load()
            settings = data.get("settings", {})
            series_map = data.get("series", {})
            events = data.get("events", [])
            unread = list(self._unread_notifications)
            self._unread_notifications.clear()

            interval_mins = float(settings.get("interval_minutes", 60))
            active_count = sum(1 for s in series_map.values() if s.get("status") == "active")

            return {
                "enabled": bool(settings.get("enabled", True)),
                "is_checking": self._is_checking,
                "interval_minutes": interval_mins,
                "default_mode": settings.get("default_mode", "latest_only"),
                "last_check_time": settings.get("last_check_time", ""),
                "monitored_count": len(series_map),
                "active_count": active_count,
                "series": list(series_map.values()),
                "events": events[-30:],
                "unread_notifications": unread,
            }

    def add_series(
        self,
        series_id: str,
        title: str = "",
        url: str = "",
        poster: str = "",
        mode: str = "latest_only",
        audio_lang: Optional[str] = None,
        subs_lang: Optional[str] = None,
        video_quality: Optional[str] = None,
        download_dir: Optional[str] = None,
        audio_fallback: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Add or update a series in the monitored watchlist."""
        clean_id = (series_id or "").strip()
        if not clean_id and url:
            clean_id = url.strip()
        if not clean_id:
            raise ValueError("Series ID is required")

        # Resolve URL inputs to series ID if passed
        if "://" in clean_id or "/" in clean_id or clean_id.startswith("series/"):
            try:
                from crunchyroll.api import parse_url_type
                kind, parsed_id = parse_url_type(clean_id)
                if kind == "series":
                    clean_id = parsed_id
                elif kind == "episode":
                    client = self.client_factory()
                    if client:
                        resp = client.do_request("GET", f"https://www.crunchyroll.com/content/v2/cms/objects/{parsed_id}")
                        if resp.status_code == 200:
                            data = resp.json().get("data", [])
                            if data:
                                ep_meta = data[0].get("episode_metadata", {})
                                ep_series_id = ep_meta.get("series_id")
                                if ep_series_id:
                                    clean_id = ep_series_id
            except Exception as e:
                logger.warning("Could not parse URL %s for watcher: %s", clean_id, e)

        with self._lock:
            data = self.store.load()
            series_map = data.get("series", {})
            now_str = _iso_now()

            existing = series_map.get(clean_id)
            known_eps = existing.get("known_episodes", []) if existing else []
            downloaded_eps = existing.get("downloaded_episodes", []) if existing else []

            clean_title = (title or "").strip()
            clean_poster = (poster or "").strip()
            clean_url = (url or "").strip()

            # When newly adding or missing metadata, query get_series
            is_switching_to_latest = existing and existing.get("mode") != "latest_only" and mode == "latest_only"
            should_fetch = (not existing and mode == "latest_only") or is_switching_to_latest or (not clean_title or clean_title == clean_id) or (not clean_poster)
            if should_fetch:
                try:
                    client = self.client_factory()
                    if client:
                        from crunchyroll.api import get_series
                        cfg = self.config_provider()
                        al = audio_lang or cfg.get("audio_lang", "ja-JP")
                        sl = subs_lang or cfg.get("subs_lang", "en-US")
                        s_meta = get_series(client, clean_id, al, sl)
                        if s_meta:
                            if mode == "latest_only" and (not existing or is_switching_to_latest or not known_eps):
                                eps = s_meta.get("episodes", [])
                                fallback_on = bool(audio_fallback) if audio_fallback is not None else bool(cfg.get("audio_fallback", True))
                                try:
                                    from crunchyroll.queue import normalize_langs
                                    wanted_audio = normalize_langs(al)
                                except Exception:
                                    wanted_audio = [al] if al else []
                                # Episodes not yet out in the requested audio stay pending:
                                # they are picked up by the next checks once the dub drops.
                                known_eps = []
                                for e in eps:
                                    eid = str(getattr(e, "id", "") or (e.get("id") if isinstance(e, dict) else "")).strip()
                                    if eid and _audio_ready(client, e, eid, wanted_audio, fallback_on):
                                        known_eps.append(eid)
                            if not clean_title or clean_title == clean_id:
                                clean_title = s_meta.get("title") or clean_title
                            if not clean_poster:
                                clean_poster = s_meta.get("poster") or clean_poster
                except Exception as e:
                    logger.warning("Could not pre-populate metadata for %s: %s", clean_id, e)

            final_title = clean_title or (existing.get("title") if existing else clean_id)
            final_poster = clean_poster or (existing.get("poster") if existing else "")
            final_url = clean_url or (existing.get("url") if existing else f"https://www.crunchyroll.com/series/{clean_id}")

            record = {
                "id": clean_id,
                "title": final_title,
                "url": final_url,
                "poster": final_poster,
                "mode": mode or (existing.get("mode") if existing else "latest_only"),
                # Re-adding (e.g. a mode change from the UI) passes no
                # overrides; keep the existing per-series settings in that
                # case instead of silently resetting them to the defaults.
                "audio_lang": audio_lang if audio_lang is not None else (existing.get("audio_lang") if existing else None),
                "subs_lang": subs_lang if subs_lang is not None else (existing.get("subs_lang") if existing else None),
                "video_quality": video_quality if video_quality is not None else (existing.get("video_quality") if existing else None),
                "download_dir": download_dir if download_dir is not None else (existing.get("download_dir") if existing else None),
                "audio_fallback": audio_fallback if audio_fallback is not None else (existing.get("audio_fallback") if existing else None),
                "known_episodes": known_eps,
                "downloaded_episodes": downloaded_eps,
                "last_checked": existing.get("last_checked", "") if existing else "",
                "last_download": existing.get("last_download", "") if existing else "",
                "last_episode_name": existing.get("last_episode_name", "") if existing else "",
                "status": "active",
                "created_at": existing.get("created_at", now_str) if existing else now_str,
            }

            series_map[clean_id] = record
            data["series"] = series_map
            self.store.save(data)
            logger.info("Monitored series updated: %s (%s)", final_title, clean_id)
            return record

    def remove_series(self, series_id: str) -> bool:
        """Stop monitoring a series and remove it from store."""
        clean_id = (series_id or "").strip()
        with self._lock:
            data = self.store.load()
            series_map = data.get("series", {})
            if clean_id in series_map:
                del series_map[clean_id]
                data["series"] = series_map
                self.store.save(data)
                logger.info("Removed series %s from watcher", clean_id)
                return True
            return False

    def toggle_series(self, series_id: str, status: Optional[str] = None) -> Optional[str]:
        """Toggle or set status ('active' | 'paused') for a monitored series."""
        clean_id = (series_id or "").strip()
        with self._lock:
            data = self.store.load()
            series_map = data.get("series", {})
            if clean_id in series_map:
                cur = series_map[clean_id].get("status", "active")
                new_st = status if status in ("active", "paused") else ("paused" if cur == "active" else "active")
                series_map[clean_id]["status"] = new_st
                data["series"] = series_map
                self.store.save(data)
                return new_st
            return None

    SERIES_OVERRIDABLE_KEYS = ("audio_lang", "subs_lang", "video_quality", "download_dir", "audio_fallback")

    def update_series(self, series_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update per-series overrides for one monitored series.

        Passing None or an empty string for an override clears it, so the
        series falls back to the global default again. Unknown keys are
        ignored. Returns the updated record, or None when not monitored.
        """
        clean_id = (series_id or "").strip()
        if not clean_id:
            return None
        with self._lock:
            data = self.store.load()
            series_map = data.get("series", {})
            if clean_id not in series_map:
                return None
            item = series_map[clean_id]

            if "mode" in updates and updates["mode"] in ("latest_only", "all_missing"):
                item["mode"] = updates["mode"]

            for key in self.SERIES_OVERRIDABLE_KEYS:
                if key not in updates:
                    continue
                val = updates[key]
                if key == "audio_fallback":
                    item[key] = None if val is None else bool(val)
                    continue
                text = str(val).strip() if val is not None else ""
                item[key] = text or None

            series_map[clean_id] = item
            data["series"] = series_map
            self.store.save(data)
            logger.info("Updated per-series settings for %s: %s", clean_id,
                        {k: updates[k] for k in updates if k in self.SERIES_OVERRIDABLE_KEYS or k == "mode"})
            return item

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update auto-downloader operational settings."""
        interval_changed = False
        enabled_turned_on = False
        with self._lock:
            data = self.store.load()
            settings = data.get("settings", {})
            prev_enabled = bool(settings.get("enabled", True))
            prev_interval = float(settings.get("interval_minutes", 60))

            if "enabled" in updates:
                new_enabled = bool(updates["enabled"])
                settings["enabled"] = new_enabled
                if new_enabled and not prev_enabled:
                    enabled_turned_on = True

            if "interval_minutes" in updates:
                try:
                    val = max(0.5, float(updates["interval_minutes"]))
                    if abs(val - prev_interval) > 1e-4:
                        settings["interval_minutes"] = val
                        interval_changed = True
                except (ValueError, TypeError):
                    pass

            if "default_mode" in updates and updates["default_mode"] in ("latest_only", "all_missing"):
                settings["default_mode"] = updates["default_mode"]

            data["settings"] = settings
            self.store.save(data)

        # Wake up worker thread so new interval / enabled state applies immediately
        if interval_changed or enabled_turned_on:
            self._wake_event.set()

        return settings

    def check_all(self, force: bool = False) -> Dict[str, Any]:
        """Scan all active monitored series for new or missing episodes."""
        with self._lock:
            if self._is_checking:
                return {"success": False, "error": "Scan already in progress", "new_episodes": 0}
            self._is_checking = True
            self._last_check_start = time.time()

        try:
            data = self.store.load()
            settings = data.get("settings", {})
            if not settings.get("enabled", True) and not force:
                return {"success": True, "message": "Watcher is currently disabled", "new_episodes": 0}

            series_map = data.get("series", {})
            active_series = [s for s in series_map.values() if s.get("status") == "active"]

            total_enqueued = 0
            scanned_count = 0
            new_events: List[Dict[str, Any]] = []

            client = self.client_factory()
            if not client:
                logger.warning("Watcher skipped check: no HTTP client available")
                return {"success": False, "error": "Not authenticated", "new_episodes": 0}

            for item in active_series:
                sid = item.get("id")
                if not sid:
                    continue
                scanned_count += 1
                try:
                    enq_count, events = self._check_single_series(client, item)
                    total_enqueued += enq_count
                    new_events.extend(events)
                except Exception as e:
                    logger.warning("Temporary network issue checking series %s (%s): %s", sid, item.get("title", sid), e)

            # Update last check timestamp
            data = self.store.load()
            data["settings"]["last_check_time"] = _iso_now()
            if new_events:
                existing_events = data.get("events", [])
                existing_events.extend(new_events)
                data["events"] = existing_events[-100:]  # Keep last 100
            self.store.save(data)

            return {
                "success": True,
                "scanned_count": scanned_count,
                "new_episodes": total_enqueued,
                "events": new_events,
            }
        finally:
            with self._lock:
                self._is_checking = False

    def check_series(self, series_id: str) -> Dict[str, Any]:
        """Scan a single monitored series immediately."""
        clean_id = (series_id or "").strip()
        data = self.store.load()
        series_map = data.get("series", {})
        item = series_map.get(clean_id)
        if not item:
            return {"success": False, "error": f"Series {clean_id} is not monitored", "new_episodes": 0}

        client = self.client_factory()
        if not client:
            return {"success": False, "error": "Not authenticated", "new_episodes": 0}

        try:
            enq_count, events = self._check_single_series(client, item)
        except Exception as e:
            logger.warning("Error checking series %s (%s): %s", clean_id, item.get("title", clean_id), e)
            return {"success": False, "error": f"Network error checking episodes: {e}", "new_episodes": 0}

        if events:
            data = self.store.load()
            existing_events = data.get("events", [])
            existing_events.extend(events)
            data["events"] = existing_events[-100:]
            self.store.save(data)

        return {
            "success": True,
            "series_id": clean_id,
            "new_episodes": enq_count,
            "events": events,
        }

    def _check_single_series(self, client: Any, item: Dict[str, Any]) -> Tuple[int, List[Dict[str, Any]]]:
        from crunchyroll.api import get_series

        sid = item["id"]
        title = item.get("title", sid)
        mode = item.get("mode", "latest_only")
        cfg = self.config_provider()

        al = item.get("audio_lang") or cfg.get("audio_lang", "ja-JP")
        sl = item.get("subs_lang") or cfg.get("subs_lang", "en-US")
        vq = item.get("video_quality") or cfg.get("video_quality", "1080p")
        aq = cfg.get("audio_quality", "192k")
        dl_dir = item.get("download_dir") or cfg.get("download_dir", "anime")

        try:
            s_meta = get_series(client, sid, al, sl)
        except Exception as e:
            logger.warning("Could not fetch episodes for %s (%s): %s", sid, title, e)
            return 0, []

        all_eps = s_meta.get("episodes", [])
        if not all_eps:
            return 0, []

        from crunchyroll.utils import is_episode_on_disk

        series_fb = item.get("audio_fallback")
        fallback_on = bool(series_fb) if series_fb is not None else bool(cfg.get("audio_fallback", True))
        try:
            from crunchyroll.queue import normalize_langs
            wanted_audio = normalize_langs(al)
        except Exception:
            wanted_audio = [al] if al else []

        known_set = set(item.get("known_episodes", []))
        downloaded_set = set(item.get("downloaded_episodes", []))
        pending_audio = set()  # episodes not yet dubbed in the requested language(s)

        # Check if the download directory exists (e.g. external drive connected)
        disk_available = os.path.isdir(os.path.abspath(os.path.expanduser((dl_dir or ".").strip())))
        if not disk_available:
            logger.warning("[watcher] Download directory '%s' is not accessible (drive disconnected?). Skipping disk-sync for '%s'.", dl_dir, title)

        to_download = []
        for ep in all_eps:
            ep_id = str(getattr(ep, "id", "") or (ep.get("id") if isinstance(ep, dict) else "")).strip()
            if not ep_id:
                continue

            ep_num = getattr(ep, "episode_number", 0) if hasattr(ep, "episode_number") else (ep.get("episode_number", 0) if isinstance(ep, dict) else 0)
            sn_num = getattr(ep, "season_number", 0) if hasattr(ep, "season_number") else (ep.get("season_number", 0) if isinstance(ep, dict) else 0)
            ep_title = getattr(ep, "title", "") if hasattr(ep, "title") else (ep.get("title", "") if isinstance(ep, dict) else "")
            sn_title = getattr(ep, "season_title", "") if hasattr(ep, "season_title") else (ep.get("season_title", "") if isinstance(ep, dict) else "")

            # Check if this episode is currently active or queued in the download queue
            is_queued_or_active = False
            if self.queue:
                try:
                    with self.queue.lock:
                        act_id = self.queue.active_job.ep_id if self.queue.active_job else None
                        q_ids = {j.ep_id for j in self.queue.queue}
                        if ep_id == act_id or ep_id in q_ids:
                            is_queued_or_active = True
                except Exception:
                    pass

            # With audio fallback off, an episode only counts as handled once it
            # exists in a requested audio language; until then it stays pending
            # (neither queued nor marked known) so a late dub is picked up.
            if not _audio_ready(client, ep, ep_id, wanted_audio, fallback_on):
                pending_audio.add(ep_id)
                known_set.discard(ep_id)  # heal state recorded before this fix
                continue

            if disk_available:
                on_disk = is_episode_on_disk(
                    base_dir=dl_dir,
                    series_title=title,
                    season_num=sn_num,
                    ep_num=ep_num,
                    ep_title=ep_title,
                    season_title=sn_title,
                    quality_tag=f" [{vq}]",
                    ext=".mkv",
                )
                if on_disk:
                    downloaded_set.add(ep_id)
                elif not is_queued_or_active:
                    # Episode missing from disk and not currently downloading
                    downloaded_set.discard(ep_id)
            else:
                on_disk = ep_id in downloaded_set

            # Mode 1: latest_only -> new episode if not in known_set and not on disk
            if mode == "latest_only":
                if ep_id not in known_set and not on_disk:
                    if not is_queued_or_active:
                        to_download.append({
                            "id": ep_id,
                            "title": ep_title,
                            "series_title": title,
                            "season_title": sn_title,
                            "season_number": sn_num,
                            "episode_number": ep_num,
                        })
            # Mode 2: all_missing -> missing if not present on disk
            elif mode == "all_missing":
                if not on_disk:
                    if not is_queued_or_active:
                        to_download.append({
                            "id": ep_id,
                            "title": ep_title,
                            "series_title": title,
                            "season_title": sn_title,
                            "season_number": sn_num,
                            "episode_number": ep_num,
                        })

        # Update known_set with all current episodes that are audio-ready;
        # episodes still waiting on a dub stay pending for the next pass.
        for ep in all_eps:
            eid = str(getattr(ep, "id", "") or (ep.get("id") if isinstance(ep, dict) else "")).strip()
            if eid and eid not in pending_audio:
                known_set.add(eid)

        events: List[Dict[str, Any]] = []
        enqueued_count = 0

        if to_download:
            batch_opts = {
                "video_quality": vq,
                "audio_quality": aq,
                "audio_lang": al,
                "subs_lang": sl,
                "force_download": False,
                "download_dir": dl_dir,
                "workers": cfg.get("workers", 16),
                "enable_hedging": cfg.get("enable_hedging", False),
                "enable_resume": cfg.get("enable_resume", True),
                "bitrate_mode": cfg.get("bitrate_mode", "highest"),
                "audio_fallback": fallback_on,
            }

            logger.info("[watcher] Detected %d new episode(s) for '%s'!", len(to_download), title)
            enq = self.queue.enqueue_batch(to_download, batch_opts, task_title=title)
            enqueued_count = len(enq)

            last_ep_name = to_download[-1]["title"] or f"Episode {to_download[-1]['episode_number']}"
            now_iso = _iso_now()

            for item_dl in to_download:
                downloaded_set.add(item_dl["id"])
                ev = {
                    "timestamp": now_iso,
                    "type": "new_episode",
                    "series_id": sid,
                    "series_title": title,
                    "episode_id": item_dl["id"],
                    "episode_title": item_dl["title"] or f"Episode {item_dl['episode_number']}",
                    "message": f"Auto-enqueued {title} - {item_dl['title'] or ('Ep ' + str(item_dl['episode_number']))}",
                }
                events.append(ev)

            with self._lock:
                self._unread_notifications.append({
                    "series_title": title,
                    "count": len(to_download),
                    "last_episode": last_ep_name,
                    "time": now_iso,
                })

        # Update series record in persistent store
        data = self.store.load()
        if sid in data.get("series", {}):
            data["series"][sid]["known_episodes"] = list(known_set)
            data["series"][sid]["downloaded_episodes"] = list(downloaded_set)
            data["series"][sid]["last_checked"] = _iso_now()
            if to_download:
                data["series"][sid]["last_download"] = _iso_now()
                data["series"][sid]["last_episode_name"] = to_download[-1]["title"] or f"Episode {to_download[-1]['episode_number']}"
            self.store.save(data)

        return enqueued_count, events

    def simulate_release(self, series_id: str) -> Dict[str, Any]:
        """Rollback helper for test & verification: removes the latest episode from seen/downloaded history."""
        clean_id = (series_id or "").strip()
        with self._lock:
            data = self.store.load()
            series_map = data.get("series", {})
            if clean_id not in series_map:
                return {"success": False, "error": f"Series {clean_id} is not monitored"}

            item = series_map[clean_id]
            known = item.get("known_episodes", [])
            downloaded = item.get("downloaded_episodes", [])

            if not known and not downloaded:
                return {"success": False, "error": "No recorded episodes to simulate release for"}

            # Remove the last known episode to simulate a new drop
            removed_id = ""
            if known:
                removed_id = known.pop()
            if removed_id in downloaded:
                downloaded.remove(removed_id)

            item["known_episodes"] = known
            item["downloaded_episodes"] = downloaded
            data["series"][clean_id] = item
            self.store.save(data)

            logger.info("Simulated new release for %s (removed ep %s from seen)", clean_id, removed_id)
            # Trigger immediate check to process it
            return self.check_series(clean_id)
