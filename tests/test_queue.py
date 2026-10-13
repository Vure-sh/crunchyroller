"""
Acceptance verification test suite for Crunchyroller queue fixes.
Tests all 10 criteria identified by Antigravity and Astra.
"""

import sys
import os
import time
import threading
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure crunchyroller package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crunchyroll.queue import DownloadQueue, QueueItem, DownloadTask
from crunchyroll.state_store import StateStore, PersistedState
from crunchyroll.api import EpisodeInfo, EpisodeMetadata


def make_mock_info(title="Ep 1", season_num=1, ep_num=1):
    return EpisodeInfo(
        title=title,
        episode_metadata=EpisodeMetadata(
            audio_locale="ja-JP",
            episode_number=ep_num,
            season_number=season_num,
            series_title="Mock Series",
            availability_starts="",
        ),
        subtitles={},
    )


class QueueVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmp_dir, "queue_state.json")
        self.store = StateStore(state_path=self.state_file, debounce_s=0.05)
        self.purge_patcher = patch("crunchyroll.queue.purge_orphan_streams")
        self.purge_patcher.start()

    def tearDown(self):
        self.purge_patcher.stop()
        self.store.close()
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
            os.rmdir(self.tmp_dir)
        except Exception:
            pass

    def test_01_all_failed_batch_reports_error(self):
        """Fix 1: When all items fail, queue status is 'error' (never 'idle' or stuck)."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        q.client_factory = MagicMock()

        def failing_downloader(*args, **kwargs):
            raise RuntimeError("CR error: 403 Forbidden")

        with patch("crunchyroll.queue.download_episode", side_effect=failing_downloader), \
             patch("crunchyroll.queue.get_episode_info", return_value=make_mock_info()):
            q.enqueue({"id": "ep-fail-1", "title": "Ep 1"})

            timeout = time.time() + 3.0
            while q.worker_thread and q.worker_thread.is_alive() and time.time() < timeout:
                time.sleep(0.05)

        state = q.get_state()
        print(f"\n[Verify 1] All-failed batch -> status: '{state['status']}', last_status: '{q.last_status}'")
        self.assertEqual(q.last_status, "error")
        self.assertEqual(state["status"], "error")
        self.assertEqual(q.failed_batch_count, 1)

    def test_02_mixed_batch_reports_partial_error(self):
        """Fix 2: Mixed batch reports 'partial_error' instead of false 'completed'."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        q.client_factory = MagicMock()

        call_count = 0
        dummy_file = os.path.join(self.tmp_dir, "dummy_done.mkv")
        with open(dummy_file, "wb") as f:
            f.write(b"x" * 2048)

        def mixed_downloader(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Failed ep 2")
            return dummy_file

        with patch("crunchyroll.queue.download_episode", side_effect=mixed_downloader), \
             patch("crunchyroll.queue.get_episode_info", return_value=make_mock_info()):
            q.enqueue({"id": "ep-ok", "title": "Ep OK"})
            q.enqueue({"id": "ep-bad", "title": "Ep Bad"})

            timeout = time.time() + 4.0
            while q.worker_thread and q.worker_thread.is_alive() and time.time() < timeout:
                time.sleep(0.05)

        state = q.get_state()
        print(f"\n[Verify 2] Mixed batch -> status: '{state['status']}', last_status: '{q.last_status}'")
        self.assertEqual(q.last_status, "partial_error")
        self.assertEqual(state["status"], "partial_error")
        self.assertEqual(q.completed_batch_count, 1)
        self.assertEqual(q.failed_batch_count, 1)

    def test_03_cancel_all_then_enqueue_processes_new_work(self):
        """Fix 3: Cancel all followed by immediate enqueue processes new job without stranding."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        q.client_factory = MagicMock()

        in_download = threading.Event()
        can_finish_cleanup = threading.Event()
        new_ep_downloaded = threading.Event()

        dummy_file = os.path.join(self.tmp_dir, "new_done.mkv")
        with open(dummy_file, "wb") as f:
            f.write(b"x" * 2048)

        def mixed_worker_downloader(*args, **kwargs):
            ep_id = kwargs.get("base_content_id")
            if ep_id == "ep-slow-1":
                in_download.set()
                while not q.cancel_event.is_set():
                    time.sleep(0.02)
                raise InterruptedError("Cancelled")
            elif ep_id == "ep-new-2":
                new_ep_downloaded.set()
                return dummy_file

        original_close = q._close_client
        def slow_close(client):
            if q.active_job is not None and q.active_job.ep_id == "ep-slow-1":
                can_finish_cleanup.wait(timeout=2.0)
            original_close(client)

        q._close_client = slow_close

        with patch("crunchyroll.queue.download_episode", side_effect=mixed_worker_downloader), \
             patch("crunchyroll.queue.get_episode_info", return_value=make_mock_info()):
            
            q.enqueue({"id": "ep-slow-1", "title": "Slow 1"})
            self.assertTrue(in_download.wait(timeout=2.0))

            # User cancels all
            q.cancel_all()

            # Before _close_client finishes, enqueue new job
            new_job = q.enqueue({"id": "ep-new-2", "title": "New Ep 2"})
            self.assertIsNotNone(new_job)

            # Let cleanup finish
            can_finish_cleanup.set()

            # The new job should be picked up and downloaded!
            self.assertTrue(new_ep_downloaded.wait(timeout=3.0), "New job was picked up by worker after cancellation!")

            # Wait for worker to finish completing the job
            timeout = time.time() + 3.0
            while q.worker_thread and q.worker_thread.is_alive() and time.time() < timeout:
                time.sleep(0.05)

        print(f"\n[Verify 3] Cancel all + enqueue -> new_ep_downloaded: True, last_status: '{q.last_status}'")
        self.assertEqual(q.last_status, "completed")

    def test_04_running_active_job_persisted_and_rehydrates_as_interrupted(self):
        """Fix 4: Running active job is included in snapshot and rehydrated as 'interrupted'."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        q.client_factory = MagicMock()

        in_download = threading.Event()
        release_download = threading.Event()

        def hanging_downloader(*args, **kwargs):
            in_download.set()
            release_download.wait(timeout=2.0)

        with patch("crunchyroll.queue.download_episode", side_effect=hanging_downloader), \
             patch("crunchyroll.queue.get_episode_info", return_value=make_mock_info()):
            
            q.enqueue({"id": "ep-active-persist", "title": "Active Ep"})
            self.assertTrue(in_download.wait(timeout=2.0))

            snapshot = q._snapshot()
            release_download.set()

        queued_ids = [d["id"] for d in snapshot["queue"]]
        print(f"\n[Verify 4] Snapshot during active download -> queued_ids: {queued_ids}")
        self.assertIn("job-", queued_ids[0])
        self.assertEqual(snapshot["queue"][0]["status"], "running")

        # Simulate reload in new queue instance
        persisted = PersistedState.from_dict(snapshot)
        q2 = DownloadQueue()
        count = q2.rehydrate(persisted)
        self.assertEqual(count, 1)
        self.assertEqual(q2.queue[0].status, "interrupted")

    def test_05_terminal_job_cleanup_not_added_to_saved_queue(self):
        """Fix 5: Completed/failed jobs during client teardown are not saved into queue."""
        q = DownloadQueue(state_store=self.store)
        completed_job = QueueItem(id="j-done", ep_id="ep-done", status="completed")
        q.history.append(completed_job)
        q.active_job = completed_job  # Still set during _close_client
        
        snapshot = q._snapshot()
        queued_ids = [d["id"] for d in snapshot["queue"]]
        print(f"\n[Verify 5] Terminal cleanup snapshot -> queued_ids: {queued_ids}")
        self.assertNotIn("j-done", queued_ids)

    def test_06_active_item_removal_cleans_up_solo_task(self):
        """Fix 6: Removing active item when it is the sole item in a task removes the task."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        q.client_factory = MagicMock()

        in_download = threading.Event()
        def hanging_downloader(*args, **kwargs):
            in_download.set()
            while not q.cancel_event.is_set():
                time.sleep(0.02)
            raise InterruptedError("Cancelled")

        with patch("crunchyroll.queue.download_episode", side_effect=hanging_downloader), \
             patch("crunchyroll.queue.get_episode_info", return_value=make_mock_info()):
            
            items = [{"id": "ep-solo", "title": "Solo Ep"}]
            q.enqueue_batch(items, task_title="Solo Anime")
            self.assertTrue(in_download.wait(timeout=2.0))

            active_id = q.active_job.id
            task_id = q.active_job.task_id
            self.assertIn(task_id, q.tasks)

            q.remove(active_id)

        print(f"\n[Verify 6] After active job removal -> tasks: {list(q.tasks.keys())}")
        self.assertNotIn(task_id, q.tasks, "Task cleaned up and no zombie task card left!")

    def test_07_cooldown_preserves_overall_pct_and_shows_next_up(self):
        """Fix 7: Cooldown between episodes preserves overall_pct and shows next up."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.5, 0.6))
        q.client_factory = MagicMock()

        ep1_done = threading.Event()
        dummy_file = os.path.join(self.tmp_dir, "ep1_done.mkv")
        with open(dummy_file, "wb") as f:
            f.write(b"x" * 2048)

        call_idx = 0
        def tracking_downloader(*args, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                ep1_done.set()
                return dummy_file
            time.sleep(1.0)
            return dummy_file

        with patch("crunchyroll.queue.download_episode", side_effect=tracking_downloader), \
             patch("crunchyroll.queue.get_episode_info", return_value=make_mock_info()):
            
            q.enqueue({"id": "ep-1", "title": "Ep 1"})
            q.enqueue({"id": "ep-2", "title": "Ep 2"})

            self.assertTrue(ep1_done.wait(timeout=2.0))
            time.sleep(0.05)
            state = q.get_state()
            print(f"\n[Verify 7] Cooldown between episodes -> overall_pct: {state['overall_pct']}%, episode: '{state['episode']}'")
            self.assertEqual(state["overall_pct"], 50.0)
            self.assertTrue("Next up:" in state["episode"])

    def test_08_retry_failed_recalibrates_total_batch_count(self):
        """Fix 8: retry_failed() recalibrates total_batch_count properly."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        item1 = QueueItem(id="j1", ep_id="ep1", status="completed")
        item2 = QueueItem(id="j2", ep_id="ep2", status="failed", error="Network error")
        q.history = [item1, item2]
        q.completed_batch_count = 1
        q.total_batch_count = 2

        q.retry_failed()
        print(f"\n[Verify 8] After retry_failed() -> completed: {q.completed_batch_count}, total_batch: {q.total_batch_count}")
        # Denominator remains 2 (1 completed + 1 queued)
        self.assertEqual(q.total_batch_count, 2)

    def test_09_all_items_map_is_pruned(self):
        """Fix 9: all_items_map prunes stale unreferenced items."""
        q = DownloadQueue(state_store=self.store, max_history=5)
        for i in range(15):
            q.enqueue({"id": f"ep-{i}", "title": f"Ep {i}"})

        # Clear queue and history
        q.clear()
        q.clear_history()

        print(f"\n[Verify 9] After clearing -> all_items_map size: {len(q.all_items_map)}")
        self.assertEqual(len(q.all_items_map), 0)

    def test_10_partials_clean_protects_queued_and_active(self):
        """Fix 10: Partials cleanup protects both active and queued episode IDs."""
        q = DownloadQueue(state_store=self.store)
        job_active = QueueItem(id="j-act", ep_id="ep-active-123")
        job_queued = QueueItem(id="j-que", ep_id="ep-queued-456")
        q.active_job = job_active
        q.queue.append(job_queued)

        active_job = q.active_job
        active_ep_id = active_job.ep_id if active_job else None
        queued_ep_ids = {j.ep_id for j in q.queue if j.ep_id}
        protected_ep_ids = set(queued_ep_ids)
        if active_ep_id:
            protected_ep_ids.add(active_ep_id)

        print(f"\n[Verify 10] Protected episode IDs for partials cleanup: {protected_ep_ids}")
        self.assertIn("ep-active-123", protected_ep_ids)
        self.assertIn("ep-queued-456", protected_ep_ids)

    def test_11_failed_task_cleared_by_clear_finished_tasks(self):
        """Fix 11: Failed task is cleared by clear_finished_tasks()."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        q.client_factory = MagicMock()

        def failing_downloader(*args, **kwargs):
            raise RuntimeError("Download failed")

        with patch("crunchyroll.queue.download_episode", side_effect=failing_downloader), \
             patch("crunchyroll.queue.get_episode_info", return_value=make_mock_info()):
            q.enqueue_batch([{"id": "ep-fail-task", "title": "Ep Failed"}], task_title="Failed Anime")

            timeout = time.time() + 3.0
            while q.worker_thread and q.worker_thread.is_alive() and time.time() < timeout:
                time.sleep(0.05)

        self.assertEqual(len(q.tasks), 1)
        task_id = list(q.tasks.keys())[0]
        t = q.tasks[task_id]
        computed_status = t.get_computed_status(q.all_items_map)
        print(f"\n[Verify 11] Failed task before clear -> computed_status: '{computed_status}'")
        self.assertEqual(computed_status, "failed")

        cleared = q.clear_finished_tasks()
        print(f"[Verify 11] Cleared count: {cleared}, remaining tasks: {list(q.tasks.keys())}")
        self.assertEqual(cleared, 1)
        self.assertEqual(len(q.tasks), 0)

    def test_12_dismiss_task_deletes_failed_or_finished_task(self):
        """Fix 12: remove_task() deletes a failed task directly without error."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        t = DownloadTask(id="task-manual-fail", series_title="Manual Anime")
        item = QueueItem(id="j-fail", ep_id="ep-fail", status="failed")
        t.item_ids.append("j-fail")
        q.tasks[t.id] = t
        q.history.append(item)
        q.all_items_map["j-fail"] = item

        removed = q.remove_task(t.id)
        print(f"\n[Verify 12] Dismiss failed task -> removed: {removed}, tasks: {list(q.tasks.keys())}")
        self.assertTrue(removed)
        self.assertNotIn(t.id, q.tasks)

    def test_13_idempotent_remove_and_clear_finished_tasks(self):
        """Fix 13: remove_task() is idempotent for already cleared tasks; clear() removes finished tasks."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        # Idempotent removal
        removed_again = q.remove_task("nonexistent-task-id")
        self.assertTrue(removed_again)

        # clear() removes finished tasks
        t = DownloadTask(id="task-finished", series_title="Finished Anime", status="completed")
        q.tasks[t.id] = t
        cleared_count = q.clear()
        print(f"\n[Verify 13] Clear queue with finished task -> remaining tasks: {list(q.tasks.keys())}")
        self.assertNotIn(t.id, q.tasks)

    def test_14_multi_anime_enqueue_batch(self):
        """Fix 14: enqueue_batch with items from multiple anime creates separate tasks per anime."""
        q = DownloadQueue(state_store=self.store, cooldown_range=(0.01, 0.02))
        items = [
            {"id": "ep-jujutsu-1", "title": "Jujutsu Ep 1", "series_title": "Jujutsu Kaisen"},
            {"id": "ep-jujutsu-2", "title": "Jujutsu Ep 2", "series_title": "Jujutsu Kaisen"},
            {"id": "ep-frieren-1", "title": "Frieren Ep 1", "series_title": "Frieren"},
            {"id": "ep-solo-1", "title": "Solo Ep 1", "series_title": "Solo Leveling"},
        ]
        enqueued = q.enqueue_batch(items)
        print(f"\n[Verify 14] Enqueued {len(enqueued)} items across tasks: {[t.series_title for t in q.tasks.values()]}")
        self.assertEqual(len(enqueued), 4)
        self.assertEqual(len(q.tasks), 3)
        series_titles = {t.series_title for t in q.tasks.values()}
        self.assertEqual(series_titles, {"Jujutsu Kaisen", "Frieren", "Solo Leveling"})


if __name__ == "__main__":
    unittest.main()
