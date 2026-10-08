"""
crunchyroll.queue — thread-safe download queue manager for batch and sequential downloads.
Supports FIFO queuing, job removal, queue clearing, pause/resume, skip, cancel, and live progress reporting.
"""

from collections import deque
from dataclasses import dataclass, field
import logging
import os
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

logger = logging.getLogger("crunchyroll.queue")

from .api import get_episode_info, purge_orphan_streams
from .downloader import download_episode
from .http_client import CrunchyrollHttpClient
from .session_pool import ConcurrencyConfig
from .state_store import PersistedState, StateStore
from .types import DEFAULT_DOWNLOAD_DIR, EpisodeInfo


@dataclass
class QueueItem:
    id: str
    ep_id: str
    title: str = ""
    season_number: int = 0
    episode_number: int = 0
    series_title: str = ""
    video_quality: str = "1080p"
    audio_quality: str = "192k"
    audio_langs: List[str] = field(default_factory=lambda: ["ja-JP"])
    subs_langs: List[str] = field(default_factory=lambda: ["en-US"])
    force_download: bool = False
    download_dir: str = DEFAULT_DOWNLOAD_DIR
    workers: int = 16
    enable_hedging: bool = False
    enable_resume: bool = True
    bitrate_mode: str = "highest"
    status: str = "queued"  # queued | running | paused | completed | failed | canceled | interrupted
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    output_file: Optional[str] = None
    file_size_mb: float = 0.0
    task_id: str = ""
    season_title: str = ""

    @property
    def label(self) -> str:
        if self.season_number > 0 and self.episode_number > 0:
            prefix = f"S{self.season_number:02d}E{self.episode_number:02d}"
            return f"{prefix} — {self.title}" if self.title else prefix
        if self.title:
            return self.title
        return self.ep_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ep_id": self.ep_id,
            "title": self.title,
            "label": self.label,
            "season_number": self.season_number,
            "episode_number": self.episode_number,
            "series_title": self.series_title,
            "season_title": self.season_title,
            "video_quality": self.video_quality,
            "audio_quality": self.audio_quality,
            "audio_langs": self.audio_langs,
            "subs_langs": self.subs_langs,
            "force_download": self.force_download,
            "download_dir": self.download_dir,
            "workers": self.workers,
            "enable_hedging": self.enable_hedging,
            "enable_resume": self.enable_resume,
            "bitrate_mode": self.bitrate_mode,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "output_file": self.output_file,
            "file_size_mb": round(self.file_size_mb, 1),
            "task_id": self.task_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QueueItem":
        return cls(
            id=str(d.get("id", "")),
            ep_id=str(d.get("ep_id", "")),
            title=str(d.get("title", "")),
            season_number=int(d.get("season_number", 0)),
            episode_number=int(d.get("episode_number", 0)),
            series_title=str(d.get("series_title", "")),
            season_title=str(d.get("season_title", "")),
            video_quality=str(d.get("video_quality", "1080p")),
            audio_quality=str(d.get("audio_quality", "192k")),
            audio_langs=list(d.get("audio_langs") or ["ja-JP"]),
            subs_langs=list(d.get("subs_langs") or ["en-US"]),
            force_download=bool(d.get("force_download", False)),
            download_dir=str(d.get("download_dir") or DEFAULT_DOWNLOAD_DIR),
            workers=int(d.get("workers", 16)),
            enable_hedging=bool(d.get("enable_hedging", False)),
            enable_resume=bool(d.get("enable_resume", True)),
            bitrate_mode=str(d.get("bitrate_mode", "highest")),
            status=str(d.get("status", "queued")),
            error=d.get("error"),
            created_at=float(d.get("created_at", time.time())),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            output_file=d.get("output_file"),
            file_size_mb=float(d.get("file_size_mb", 0.0)),
            task_id=str(d.get("task_id", "")),
        )


@dataclass
class DownloadTask:
    id: str
    series_title: str
    video_quality: str = "1080p"
    audio_quality: str = "192k"
    audio_langs: List[str] = field(default_factory=lambda: ["ja-JP"])
    subs_langs: List[str] = field(default_factory=lambda: ["en-US"])
    status: str = "queued"  # queued | running | paused | completed | canceled | failed | interrupted
    item_ids: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_persisted_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "series_title": self.series_title,
            "video_quality": self.video_quality,
            "audio_quality": self.audio_quality,
            "audio_langs": self.audio_langs,
            "subs_langs": self.subs_langs,
            "status": self.status,
            "item_ids": self.item_ids,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DownloadTask":
        return cls(
            id=str(d.get("id", "")),
            series_title=str(d.get("series_title", "")),
            video_quality=str(d.get("video_quality", "1080p")),
            audio_quality=str(d.get("audio_quality", "192k")),
            audio_langs=list(d.get("audio_langs") or ["ja-JP"]),
            subs_langs=list(d.get("subs_langs") or ["en-US"]),
            status=str(d.get("status", "queued")),
            item_ids=list(d.get("item_ids") or []),
            created_at=float(d.get("created_at", time.time())),
        )

    def get_computed_status(
        self,
        items_map: Dict[str, QueueItem],
        active_job_id: Optional[str] = None,
    ) -> str:
        task_items = [items_map[iid] for iid in self.item_ids if iid in items_map]
        active_items = [it for it in task_items if it.status != "canceled"]
        total = len(active_items)
        completed = sum(1 for it in active_items if it.status == "completed")
        failed = sum(1 for it in active_items if it.status == "failed")
        canceled = sum(1 for it in task_items if it.status == "canceled")
        is_active = any(it.id == active_job_id for it in active_items)

        if self.status == "canceled":
            return "canceled"
        elif is_active:
            return "paused" if any(it.status == "paused" for it in active_items) else "running"
        elif completed == total and total > 0:
            return "completed"
        elif total == 0 and canceled > 0:
            return "canceled"
        elif completed + failed == total and total > 0:
            return "failed" if failed > 0 else "canceled"
        elif any(it.status == "paused" for it in active_items):
            return "paused"
        elif any(it.status == "queued" for it in active_items):
            return "queued"
        else:
            return self.status

    def is_finished(
        self,
        items_map: Dict[str, QueueItem],
        active_job_id: Optional[str] = None,
    ) -> bool:
        st = self.get_computed_status(items_map, active_job_id=active_job_id)
        return st in ("completed", "canceled", "failed")

    def to_dict(
        self,
        items_map: Dict[str, QueueItem],
        active_job_id: Optional[str] = None,
        active_progress_pct: float = 0.0,
    ) -> Dict[str, Any]:
        task_items = [items_map[iid] for iid in self.item_ids if iid in items_map]
        active_items = [it for it in task_items if it.status != "canceled"]
        total = len(active_items)
        completed = sum(1 for it in active_items if it.status == "completed")
        failed = sum(1 for it in active_items if it.status == "failed")
        canceled = sum(1 for it in task_items if it.status == "canceled")
        is_active = any(it.id == active_job_id for it in active_items)

        if total == 0:
            progress = 0.0
        elif completed == total:
            progress = 100.0
        else:
            base = completed / total
            active_slice = (active_progress_pct / 100.0) / total if is_active else 0.0
            progress = round(min(99.9, (base + active_slice) * 100.0), 1)

        st = self.get_computed_status(items_map, active_job_id=active_job_id)
        if st in ("completed", "canceled", "failed"):
            self.status = st

        episodes_list = []
        for it in task_items:
            ep_dict = it.to_dict()
            if it.id == active_job_id:
                ep_dict["progress"] = active_progress_pct
                ep_dict["status"] = "paused" if st == "paused" else "running"
            episodes_list.append(ep_dict)

        return {
            "id": self.id,
            "title": self.series_title or "Anime Download",
            "series_title": self.series_title or "Anime Download",
            "status": st,
            "total": total,
            "completed": completed,
            "failed": failed,
            "canceled": canceled,
            "progress_pct": progress,
            "video_quality": self.video_quality,
            "audio_quality": self.audio_quality,
            "audio_langs": self.audio_langs,
            "subs_langs": self.subs_langs,
            "episodes": episodes_list,
            "created_at": self.created_at,
        }


def normalize_langs(val: Any) -> List[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()] or ["ja-JP"]
    if isinstance(val, str):
        return [str(x).strip() for x in val.split(",") if str(x).strip()] or ["ja-JP"]
    return ["ja-JP"]


class DownloadQueue:
    def __init__(
        self,
        client_factory: Optional[Callable[[], CrunchyrollHttpClient]] = None,
        pause_event: Optional[threading.Event] = None,
        cancel_event: Optional[threading.Event] = None,
        lock: Optional[threading.RLock] = None,
        cooldown_range: tuple = (1.5, 2.5),
        cooldown_provider: Optional[Callable[[], float]] = None,
        max_history: int = 50,
        state_store: Optional[StateStore] = None,
    ):
        self.lock = lock or threading.RLock()
        self.pause_event = pause_event or threading.Event()
        if pause_event is None:
            self.pause_event.set()
        self.cancel_event = cancel_event or threading.Event()

        self.client_factory = client_factory or (lambda: CrunchyrollHttpClient())
        self.cooldown_range = cooldown_range
        self.cooldown_provider = cooldown_provider
        self.max_history = max_history
        self.state_store = state_store

        self.queue: deque[QueueItem] = deque()
        self.active_job: Optional[QueueItem] = None
        self.history: List[QueueItem] = []
        self.tasks: Dict[str, DownloadTask] = {}
        self.all_items_map: Dict[str, QueueItem] = {}
        self.worker_thread: Optional[threading.Thread] = None
        self.cancel_all_flag: bool = False

        # Live progress metrics
        self.current_seg: int = 0
        self.total_segs: int = 0
        self.speed: str = ""
        self.track: str = ""
        self.track_pct: float = 0.0
        self.overall_pct: float = 0.0
        self.complete_file: bool = False
        self.log_messages: List[str] = []

        # Batch counts for progress tracking
        self.completed_batch_count: int = 0
        self.total_batch_count: int = 0
        self.last_status: str = "idle"

        if self.state_store:
            persisted = self.state_store.load()
            self.rehydrate(persisted)

    def _snapshot(self) -> Dict[str, Any]:
        with self.lock:
            q_list = [j.to_dict() for j in self.queue]
            h_list = [j.to_dict() for j in self.history[-self.max_history:]]
            t_list = [t.to_persisted_dict() for t in self.tasks.values()]
            return {
                "schema": 1,
                "saved_at": time.time(),
                "tasks": t_list,
                "queue": q_list,
                "history": h_list,
            }

    def _trigger_save(self) -> None:
        if self.state_store:
            snapshot = self._snapshot()
            self.state_store.schedule_save(snapshot)

    def rehydrate(self, state: PersistedState) -> int:
        with self.lock:
            count = 0
            self.history = [QueueItem.from_dict(d) for d in state.history][-self.max_history:]
            for it in self.history:
                self.all_items_map[it.id] = it

            for td in state.tasks:
                task = DownloadTask.from_dict(td)
                self.tasks[task.id] = task

            restored_queue = []
            for d in state.queue:
                it = QueueItem.from_dict(d)
                if it.status in ("running", "paused"):
                    it.status = "interrupted"
                restored_queue.append(it)
                self.all_items_map[it.id] = it
                count += 1

            self.queue = deque(restored_queue)
            self.total_batch_count = len(self.queue)
            self.completed_batch_count = 0
            if count > 0:
                self.log(f"rehydrated {count} item(s) from persistent state")
            return count

    def resume_interrupted(self) -> int:
        with self.lock:
            resumed = 0
            for it in self.queue:
                if it.status == "interrupted":
                    it.status = "queued"
                    resumed += 1
            if resumed > 0:
                self.log(f"resumed {resumed} interrupted download(s)")
                self._trigger_save()
                self._ensure_worker_running()
            return resumed

    def retry_failed(self) -> int:
        with self.lock:
            retried = 0
            failed_items = [it for it in self.history if it.status == "failed"]
            self.history = [it for it in self.history if it.status != "failed"]
            for it in failed_items:
                it.status = "queued"
                it.error = None
                self.queue.append(it)
                retried += 1
            if retried > 0:
                self.total_batch_count += retried
                self.log(f"re-enqueued {retried} failed download(s)")
                self._trigger_save()
                self._ensure_worker_running()
            return retried

    def log(self, msg: str):
        logger.info("%s", msg)
        with self.lock:
            self.log_messages.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            if len(self.log_messages) > 200:
                self.log_messages.pop(0)

    @staticmethod
    def _close_client(client) -> None:
        """Best-effort close of a per-job HTTP client, freeing its session pool."""
        if client is None:
            return
        close_fn = getattr(client, "close", None)
        if not callable(close_fn):
            return
        try:
            close_fn()
        except Exception:
            pass

    @property
    def queued_count(self) -> int:
        with self.lock:
            return len(self.queue)

    def enqueue(
        self,
        item: Any,
        default_options: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        task_title: Optional[str] = None,
    ) -> Optional[QueueItem]:
        """Enqueue a single episode item. Returns the created QueueItem or None if duplicate."""
        opts = default_options or {}
        if isinstance(item, dict):
            ep_id = str(item.get("id") or item.get("ep_id") or "").strip()
            title = str(item.get("title") or "").strip()
            series_title = str(item.get("series_title") or task_title or opts.get("series_title") or "").strip()
            season_num = int(item.get("season_number") or 0)
            ep_num = int(item.get("episode_number") or 0)
            vq = str(item.get("video_quality") or opts.get("video_quality") or "1080p")
            aq = str(item.get("audio_quality") or opts.get("audio_quality") or "192k")
            al = normalize_langs(item.get("audio_langs") or item.get("audio_lang") or opts.get("audio_lang") or ["ja-JP"])
            sl = normalize_langs(item.get("subs_langs") or item.get("subs_lang") or opts.get("subs_lang") or ["en-US"])
            fd = bool(item.get("force_download", opts.get("force_download", False)))
            dl_dir = str(item.get("download_dir") or opts.get("download_dir") or DEFAULT_DOWNLOAD_DIR).strip() or DEFAULT_DOWNLOAD_DIR
            workers = int(item.get("workers") or opts.get("workers") or 16)
            enable_hedging = bool(item.get("enable_hedging", opts.get("enable_hedging", False)))
            enable_resume = bool(item.get("enable_resume", opts.get("enable_resume", True)))
            bitrate_mode = str(item.get("bitrate_mode") or opts.get("bitrate_mode") or "highest")
            season_title = str(item.get("season_title") or opts.get("season_title") or "").strip()
        else:
            ep_id = str(item).strip()
            title = ""
            series_title = str(task_title or opts.get("series_title") or "").strip()
            season_num = 0
            ep_num = 0
            vq = str(opts.get("video_quality") or "1080p")
            aq = str(opts.get("audio_quality") or "192k")
            al = normalize_langs(opts.get("audio_lang") or ["ja-JP"])
            sl = normalize_langs(opts.get("subs_lang") or ["en-US"])
            fd = bool(opts.get("force_download", False))
            dl_dir = str(opts.get("download_dir") or DEFAULT_DOWNLOAD_DIR).strip() or DEFAULT_DOWNLOAD_DIR
            workers = int(opts.get("workers") or 16)
            enable_hedging = bool(opts.get("enable_hedging", False))
            enable_resume = bool(opts.get("enable_resume", True))
            bitrate_mode = str(opts.get("bitrate_mode") or "highest")
            season_title = str(opts.get("season_title") or "").strip()

        if not ep_id:
            return None

        with self.lock:
            # Deduplicate if already queued or active
            active_id = self.active_job.ep_id if self.active_job else None
            queued_ids = {j.ep_id for j in self.queue}
            if ep_id == active_id or ep_id in queued_ids:
                return None

            job_id = f"job-{uuid.uuid4().hex[:8]}"
            job = QueueItem(
                id=job_id,
                ep_id=ep_id,
                title=title,
                season_number=season_num,
                episode_number=ep_num,
                series_title=series_title,
                video_quality=vq,
                audio_quality=aq,
                audio_langs=al,
                subs_langs=sl,
                force_download=fd,
                download_dir=dl_dir,
                workers=workers,
                enable_hedging=enable_hedging,
                enable_resume=enable_resume,
                bitrate_mode=bitrate_mode,
                status="queued",
                task_id=task_id or "",
                season_title=season_title,
            )
            self.queue.append(job)
            self.all_items_map[job.id] = job

            if self.active_job is None and len(self.queue) == 1:
                # Reset counters for a fresh batch
                self.completed_batch_count = 0
                self.total_batch_count = 1
                self.last_status = "running"
                self.overall_pct = 0.0
                self.cancel_event.clear()
                self.pause_event.set()
                self.cancel_all_flag = False
            else:
                self.total_batch_count += 1

            self._ensure_worker_running()
            self._trigger_save()
            return job

    def enqueue_batch(
        self,
        items: List[Any],
        default_options: Optional[Dict[str, Any]] = None,
        task_title: Optional[str] = None,
    ) -> List[QueueItem]:
        """Enqueue multiple episodes sequentially under an anime task."""
        opts = default_options or {}
        anime_name = str(task_title or opts.get("task_title") or opts.get("series_title") or "").strip()
        if not anime_name and items and isinstance(items[0], dict):
            anime_name = str(items[0].get("series_title") or "").strip()
        if not anime_name:
            anime_name = "Anime"

        vq = str(opts.get("video_quality") or "1080p")
        aq = str(opts.get("audio_quality") or "192k")
        al = normalize_langs(opts.get("audio_lang") or ["ja-JP"])
        sl = normalize_langs(opts.get("subs_lang") or ["en-US"])

        task_id = f"task-{uuid.uuid4().hex[:8]}"
        task = DownloadTask(
            id=task_id,
            series_title=anime_name,
            video_quality=vq,
            audio_quality=aq,
            audio_langs=al,
            subs_langs=sl,
        )

        enqueued: List[QueueItem] = []
        for it in items:
            item_opts = dict(opts)
            item_opts["series_title"] = anime_name
            job = self.enqueue(it, item_opts, task_id=task_id)
            if job:
                task.item_ids.append(job.id)
                enqueued.append(job)

        if task.item_ids:
            with self.lock:
                self.tasks[task_id] = task
        self._trigger_save()
        return enqueued

    def remove(self, job_id: str) -> bool:
        """Remove a pending job from the queue by ID or ep_id."""
        with self.lock:
            target = None
            for j in self.queue:
                if j.id == job_id or j.ep_id == job_id:
                    target = j
                    break
            if target:
                self.queue.remove(target)
                target.status = "canceled"
                if target.task_id and target.task_id in self.tasks:
                    task = self.tasks[target.task_id]
                    if target.id in task.item_ids:
                        task.item_ids.remove(target.id)
                    if not task.item_ids:
                        del self.tasks[target.task_id]
                if target.id in self.all_items_map:
                    del self.all_items_map[target.id]
                self.total_batch_count = max(
                    self.completed_batch_count + (1 if self.active_job else 0),
                    self.total_batch_count - 1,
                )
                self.log(f"Removed from queue: {target.label}")
                self._trigger_save()
                return True
            if self.active_job and (self.active_job.id == job_id or self.active_job.ep_id == job_id):
                if self.active_job.task_id and self.active_job.task_id in self.tasks:
                    task = self.tasks[self.active_job.task_id]
                    if self.active_job.id in task.item_ids:
                        task.item_ids.remove(self.active_job.id)
                self.cancel_current(job_id=job_id)
                self._trigger_save()
                return True
        return False

    def remove_task(self, task_id: str) -> bool:
        """Cancel/remove an entire anime task and its queued episodes."""
        with self.lock:
            if task_id not in self.tasks:
                return False
            task = self.tasks[task_id]
            active_id = self.active_job.id if self.active_job else None
            if task.is_finished(self.all_items_map, active_job_id=active_id):
                del self.tasks[task_id]
                self.log(f"Dismissed task: {task.series_title}")
                self._trigger_save()
                return True

            task.status = "canceled"
            # Cancel active job if it belongs to this task
            if self.active_job and self.active_job.id in task.item_ids:
                self.cancel_current()

            # Remove pending episodes from queue
            removed_count = 0
            to_remove = [j for j in self.queue if j.id in task.item_ids]
            for j in to_remove:
                self.queue.remove(j)
                j.status = "canceled"
                removed_count += 1

            self.total_batch_count = max(self.completed_batch_count, self.total_batch_count - removed_count)
            self.log(f"Canceled task: {task.series_title} ({removed_count} item(s) removed)")
            self._trigger_save()
            return True

    def clear_finished_tasks(self) -> int:
        """Clear all completed, canceled, or failed tasks."""
        with self.lock:
            active_id = self.active_job.id if self.active_job else None
            finished = [
                tid for tid, t in self.tasks.items()
                if t.is_finished(self.all_items_map, active_job_id=active_id) or len(t.item_ids) == 0
            ]
            for tid in finished:
                del self.tasks[tid]
            if finished:
                self.log(f"Cleared {len(finished)} finished task(s).")
                self._trigger_save()
            return len(finished)

    def clear_tasks(self, include_active: bool = False) -> int:
        """Clear tasks. If include_active is False, only clears finished tasks."""
        with self.lock:
            if not include_active:
                return self.clear_finished_tasks()
            count = len(self.tasks)
            if self.active_job and self.active_job.task_id:
                self.cancel_current()
            for j in list(self.queue):
                if j.task_id:
                    j.status = "canceled"
                    self.queue.remove(j)
            self.tasks.clear()
            self.log(f"All tasks cleared ({count} task(s)).")
            self._trigger_save()
            return count

    def clear(self) -> int:
        """Clear all pending jobs in the queue and remove finished tasks."""
        with self.lock:
            count = len(self.queue)
            for j in self.queue:
                j.status = "canceled"
                if j.task_id and j.task_id in self.tasks:
                    task = self.tasks[j.task_id]
                    if j.id in task.item_ids:
                        task.item_ids.remove(j.id)
            self.queue.clear()
            self.total_batch_count = self.completed_batch_count + (1 if self.active_job else 0)
            tot_batch = max(1, self.total_batch_count)
            self.overall_pct = round((self.completed_batch_count / tot_batch) * 100, 1)
            active_id = self.active_job.id if self.active_job else None
            finished_tasks = [
                tid for tid, t in self.tasks.items()
                if t.is_finished(self.all_items_map, active_job_id=active_id) or len(t.item_ids) == 0
            ]
            for tid in finished_tasks:
                del self.tasks[tid]
            self.log(f"Queue cleared ({count} item(s) removed).")
            self._trigger_save()
            return count

    def pause(self):
        """Pause active download."""
        self.pause_event.clear()
        with self.lock:
            if self.active_job and self.active_job.status == "running":
                self.active_job.status = "paused"
            self.speed = "paused"
            self.last_status = "paused"
        self.log("Download paused by user")

    def resume(self):
        """Resume paused download."""
        self.pause_event.set()
        with self.lock:
            if self.active_job and self.active_job.status == "paused":
                self.active_job.status = "running"
            self.last_status = "running"
        self.log("Download resumed by user")

    def cancel_current(self, job_id: Optional[str] = None):
        """Cancel/skip active episode and proceed to next in queue."""
        with self.lock:
            if not self.active_job:
                return
            if job_id and self.active_job.id != job_id and self.active_job.ep_id != job_id:
                return
            if self.active_job.status in ("completed", "canceled", "failed"):
                return
            self.active_job.status = "canceled"
            self.cancel_event.set()
            self.pause_event.set()  # Unblock if paused
            self.log(f"Skipped active episode: {self.active_job.label}")

    def cancel_all(self):
        """Cancel active download and clear all upcoming queue items."""
        with self.lock:
            self.cancel_all_flag = True
            cleared = len(self.queue)
            for j in self.queue:
                j.status = "canceled"
            self.queue.clear()
            for t in self.tasks.values():
                if t.status in ("queued", "running"):
                    t.status = "canceled"
            self.total_batch_count = self.completed_batch_count
            self.last_status = "canceled"
            self.speed = ""
            self.track = "canceled"
            if self.active_job:
                self.active_job.status = "canceled"
        self.cancel_event.set()
        self.pause_event.set()
        self.log(f"All downloads cancelled and queue cleared ({cleared} removed).")

    def get_queue_list(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [j.to_dict() for j in list(self.queue)]

    def get_history_list(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [j.to_dict() for j in reversed(self.history)]

    def clear_history(self) -> int:
        """Clear download history."""
        with self.lock:
            count = len(self.history)
            self.history.clear()
            self._trigger_save()
            return count

    def get_active_job(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.active_job.to_dict() if self.active_job else None

    def get_tasks_list(self) -> List[Dict[str, Any]]:
        with self.lock:
            active_id = self.active_job.id if self.active_job else None
            tasks_sorted = sorted(self.tasks.values(), key=lambda t: t.created_at)
            return [
                t.to_dict(self.all_items_map, active_job_id=active_id, active_progress_pct=self.track_pct)
                for t in tasks_sorted
            ]

    def get_state(self) -> Dict[str, Any]:
        """Return standardized state dict compatible with web GUI status panel and queue."""
        with self.lock:
            if self.cancel_all_flag:
                status = "canceled"
            elif self.active_job:
                if self.active_job.status == "canceled":
                    status = "running" if len(self.queue) > 0 else "canceled"
                else:
                    status = "paused" if not self.pause_event.is_set() else "running"
            elif len(self.queue) > 0:
                status = "running"
            elif self.last_status in ("canceled", "completed", "error"):
                status = self.last_status
            else:
                status = "idle"

            tot_batch = max(1, self.total_batch_count)
            ep_idx = min(self.completed_batch_count, tot_batch - 1)
            if status == "completed":
                ep_idx = tot_batch
                overall_pct = 100.0
                track_pct = 100.0
                episode_label = "all done"
            elif self.active_job:
                episode_label = self.active_job.label
                overall_pct = self.overall_pct
                track_pct = self.track_pct
            else:
                episode_label = ""
                overall_pct = 0.0
                track_pct = 0.0

            return {
                "status": status,
                "episode": episode_label,
                "track": self.track,
                "segs_done": self.current_seg,
                "segs_total": self.total_segs,
                "speed": self.speed,
                "overall_pct": overall_pct,
                "track_pct": track_pct,
                "ep_idx": ep_idx,
                "ep_total": tot_batch,
                "complete_file": self.complete_file,
                "log": list(self.log_messages[-100:]),
                "queued_count": len(self.queue),
                "queue": [j.to_dict() for j in list(self.queue)],
                "active_job": self.active_job.to_dict() if self.active_job else None,
                "history": [j.to_dict() for j in list(self.history[-10:])],
                "tasks": self.get_tasks_list(),
            }

    def _ensure_worker_running(self):
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()

    def _update_progress(self, job: QueueItem, cur: int, tot: int, speed: str, status: Any):
        track_type = str(status).lower() if status else "video"
        frac = (cur / tot) if tot > 0 else 0.0
        complete_file = track_type.endswith("-file")
        if complete_file:
            track_type = track_type[:-5]

        is_paused = track_type.endswith("-paused") or not self.pause_event.is_set()
        if track_type.endswith("-paused"):
            track_type = track_type[:-7]

        if "audio-only" in track_type:
            within_ep = frac * 0.95
            display_track = "audio"
        elif "audio" in track_type:
            within_ep = frac * 0.15
            display_track = "audio"
        elif "mux" in track_type:
            within_ep = 0.98
            display_track = "muxing"
        elif "done" in track_type:
            within_ep = 1.0
            display_track = "done"
        else:
            within_ep = 0.15 + (frac * 0.80)
            display_track = "video"

        with self.lock:
            prev_track = getattr(self, "_last_phase_track", None)
            if display_track != prev_track:
                self._last_phase_track = display_track
                if display_track == "audio":
                    self.log_messages.append(f"[{time.strftime('%H:%M:%S')}] downloading audio ({job.audio_quality})...")
                elif display_track == "video":
                    self.log_messages.append(f"[{time.strftime('%H:%M:%S')}] downloading video ({job.video_quality})...")
                elif display_track == "muxing":
                    self.log_messages.append(f"[{time.strftime('%H:%M:%S')}] muxing {job.label}...")
                if len(self.log_messages) > 200:
                    self.log_messages.pop(0)

            tot_batch = max(1, self.total_batch_count)
            comp_batch = self.completed_batch_count
            ep_base = (comp_batch / tot_batch) * 100
            ep_slice = (1 / tot_batch) * 100
            overall = round(ep_base + (within_ep * ep_slice), 1)
            cap = round(((comp_batch + 1) / tot_batch) * 100 - 0.1, 1)

            self.current_seg = cur
            self.total_segs = tot
            self.speed = "paused" if is_paused else (speed or "")
            self.track = display_track
            self.track_pct = round(within_ep * 100.0, 1) if "mux" not in track_type else 98.0
            self.overall_pct = min(overall, cap)
            self.complete_file = complete_file
            if is_paused:
                job.status = "paused"
                self.last_status = "paused"
            elif job.status == "paused":
                job.status = "running"
                self.last_status = "running"

    def _worker_loop(self):
        first_item = True
        while True:
            # Respect pause between jobs
            while not self.pause_event.is_set():
                if self.cancel_all_flag:
                    break
                time.sleep(0.2)

            with self.lock:
                if self.cancel_all_flag or not self.queue:
                    self.active_job = None
                    if self.completed_batch_count > 0 and not self.cancel_all_flag:
                        self.last_status = "completed"
                        self.track = "done"
                        self.speed = ""
                    elif self.cancel_all_flag:
                        self.last_status = "canceled"
                    else:
                        self.last_status = "idle"
                    self.cancel_all_flag = False
                    self.cancel_event.clear()
                    self.worker_thread = None
                    return

                needs_cooldown = not first_item and not self.cancel_all_flag
            if first_item:
                purge_client = None
                try:
                    purge_client = self.client_factory()
                    purge_orphan_streams(purge_client, all_devices=True)
                except Exception as ex:
                    self.log(f"session preflight: {ex}")
                finally:
                    self._close_client(purge_client)
                first_item = False

            # Jittered cooldown between consecutive items in batch
            # Runs while active_job is None so cancel_current() cannot accidentally cancel next job during cooldown!
            if needs_cooldown:
                if callable(self.cooldown_provider):
                    try:
                        cooldown = float(self.cooldown_provider())
                    except Exception:
                        cooldown = random.uniform(*self.cooldown_range)
                else:
                    cooldown = random.uniform(*self.cooldown_range)

                if cooldown >= 2.0:
                    self.log(f"anti-ratelimit: pausing {cooldown:.1f}s before next episode...")

                end_time = time.time() + cooldown
                while time.time() < end_time:
                    if self.cancel_all_flag:
                        break
                    time.sleep(0.05)

            with self.lock:
                if self.cancel_all_flag or not self.queue:
                    continue

                job = self.queue.popleft()
                self.active_job = job
                job.status = "running"
                job.started_at = time.time()
                self.last_status = "running"
                self.current_seg = 0
                self.total_segs = 0
                self.speed = ""
                self.track = "starting"
                self.track_pct = 0.0
                self._last_phase_track = None
                if not self.cancel_all_flag:
                    self.cancel_event.clear()

            self.log(f"[{self.completed_batch_count + 1}/{self.total_batch_count}] {job.label} [{job.video_quality}/{job.audio_quality}]")

            client = None
            try:
                if self.cancel_all_flag or job.status == "canceled":
                    raise InterruptedError("Episode cancelled")

                client = self.client_factory()
                info = None
                try:
                    info = get_episode_info(client, job.ep_id)
                    if info and info.episode_metadata:
                        with self.lock:
                            if not job.title and info.title:
                                job.title = info.title
                            if not job.season_number and info.episode_metadata.season_number:
                                job.season_number = info.episode_metadata.season_number
                            if not job.episode_number and info.episode_metadata.episode_number:
                                job.episode_number = info.episode_metadata.episode_number
                            if not job.series_title and info.episode_metadata.series_title:
                                job.series_title = info.episode_metadata.series_title
                            if not job.season_title and getattr(info.episode_metadata, "season_title", ""):
                                job.season_title = info.episode_metadata.season_title
                            elif job.season_title and not getattr(info.episode_metadata, "season_title", ""):
                                info.episode_metadata.season_title = job.season_title
                except Exception as ex:
                    self.log(f"metadata fetch error for {job.ep_id}: {ex}")
                    raise RuntimeError(f"Could not load episode metadata for {job.ep_id}: {ex}") from ex

                if not info or not info.episode_metadata:
                    raise RuntimeError(f"Could not load episode metadata for {job.ep_id}. Check login or session.")

                # Ensure cancel_event is clean before starting download unless cancel was requested
                # for THIS job or cancel_all
                if self.cancel_all_flag or job.status == "canceled":
                    raise InterruptedError("Episode cancelled")

                def _cb(title, cur, tot, speed, status):
                    self._update_progress(job, cur, tot, speed, status)

                output_file = download_episode(
                    client=client,
                    base_content_id=job.ep_id,
                    info=info,
                    audio_langs=job.audio_langs,
                    subs_langs=job.subs_langs,
                    video_quality=job.video_quality,
                    audio_quality=job.audio_quality,
                    progress_cb=_cb,
                    force_download=job.force_download,
                    pause_event=self.pause_event,
                    cancel_event=self.cancel_event,
                    download_dir=job.download_dir,
                    resume=getattr(job, "enable_resume", True),
                    bitrate_mode=getattr(job, "bitrate_mode", "highest"),
                    concurrency_config=ConcurrencyConfig(
                        min_workers=1 if getattr(job, "workers", 16) <= 2 else max(2, getattr(job, "workers", 16) // 2),
                        max_workers=max(1, min(32, getattr(job, "workers", 16))),
                        initial_workers=max(1, min(32, getattr(job, "workers", 16))),
                        pool_size=max(4, min(64, getattr(job, "workers", 16) * 2)),
                        hedging_enabled=bool(getattr(job, "enable_hedging", False)),
                    ),
                )

                if output_file and os.path.exists(output_file) and os.path.getsize(output_file) > 1024:
                    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
                    with self.lock:
                        job.output_file = output_file
                        job.file_size_mb = file_size_mb
                        job.status = "completed"
                        job.finished_at = time.time()
                        self.completed_batch_count += 1
                        self.track = "done"
                        self.track_pct = 100.0
                        tot_batch = max(1, self.total_batch_count)
                        self.overall_pct = round((self.completed_batch_count / tot_batch) * 100, 1)
                        self.history.append(job)
                        if len(self.history) > self.max_history:
                            self.history.pop(0)
                    self._trigger_save()
                    self.log(f"done: {job.label} ({file_size_mb:.1f} MB)")
                else:
                    raise RuntimeError(f"Download finished but output file missing: {output_file}")

            except Exception as e:
                if self.cancel_event.is_set() or isinstance(e, InterruptedError) or self.cancel_all_flag or job.status == "canceled":
                    with self.lock:
                        job.status = "canceled"
                        job.finished_at = time.time()
                        self.history.append(job)
                        if len(self.history) > self.max_history:
                            self.history.pop(0)
                        if not self.cancel_all_flag:
                            # Shrink total batch volume for canceled episode
                            self.total_batch_count = max(
                                self.completed_batch_count,
                                self.total_batch_count - 1,
                            )
                            tot_batch = max(1, self.total_batch_count)
                            self.overall_pct = round((self.completed_batch_count / tot_batch) * 100, 1)
                            if len(self.queue) > 0:
                                self.last_status = "running"
                            else:
                                self.last_status = "canceled" if self.completed_batch_count == 0 else "completed"
                    self._trigger_save()
                    self.log(f"canceled: {job.label}")
                else:
                    with self.lock:
                        job.status = "failed"
                        job.error = str(e)
                        job.finished_at = time.time()
                        self.history.append(job)
                        if len(self.history) > self.max_history:
                            self.history.pop(0)
                    self._trigger_save()
                    logger.error("Download failed for %s: %s", job.label, e, exc_info=True)
                    self.log(f"failed: {job.label} — {e}")
            finally:
                self._close_client(client)
                with self.lock:
                    self.active_job = None
                    if not self.cancel_all_flag:
                        self.cancel_event.clear()
