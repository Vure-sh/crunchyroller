"""High-performance HTTP session pooling, AIMD concurrency scaling, and tail-latency hedging."""

import collections
import logging
import queue
import socket
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Dict, Generator, List, Optional, Tuple, Union
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
import urllib3
from urllib3.connection import HTTPConnection
from urllib3.util.retry import Retry

logger = logging.getLogger("crunchyroll.session_pool")


class RateLimitGate:
    """Thread-safe circuit breaker / rate-limit gate to pause requests across all threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._paused_until = 0.0

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return time.monotonic() < self._paused_until

    def trigger_pause(self, wait_seconds: float) -> None:
        with self._lock:
            target = time.monotonic() + max(0.0, float(wait_seconds))
            if target > self._paused_until:
                self._paused_until = target

    def wait_if_paused(self) -> None:
        while True:
            with self._lock:
                remaining = self._paused_until - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.2))


@dataclass
class ConcurrencyConfig:
    """Configuration for concurrency, scaling, connection pool, and hedging."""
    min_workers: int = 4
    max_workers: int = 8
    initial_workers: int = 6
    aimd_enabled: bool = True
    hedging_enabled: bool = False  # disabled: hedge timeout math kills downloads on slow CDN segments
    hedge_factor: float = 2.0  # multiplier of median latency to trigger hedge
    hedge_min_delay: float = 1.5  # minimum delay in seconds before hedging
    max_retries: int = 5
    backoff_factor: float = 0.5
    pool_size: int = 16
    timeout: int = 10
    chunk_size: int = 524288  # 512 KB read buffer


class TCPKeepAliveAdapter(HTTPAdapter):
    """Custom HTTPAdapter configuring TCP Keep-Alive and TCP_NODELAY."""

    def init_poolmanager(self, *args, **kwargs):
        socket_options = list(HTTPConnection.default_socket_options)
        if hasattr(socket, "SO_KEEPALIVE"):
            socket_options.append((socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1))
        if hasattr(socket, "IPPROTO_TCP") and hasattr(socket, "TCP_NODELAY"):
            socket_options.append((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1))
        if hasattr(socket, "IPPROTO_TCP") and hasattr(socket, "TCP_KEEPIDLE"):
            socket_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15))
        if hasattr(socket, "IPPROTO_TCP") and hasattr(socket, "TCP_KEEPINTVL"):
            socket_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5))
        # Note: Do not set SO_RCVBUF on Windows as it disables Windows TCP Receive Window Auto-Tuning.
        kwargs["socket_options"] = socket_options
        super().init_poolmanager(*args, **kwargs)


class AIMDConcurrencyScaler:
    """Additive Increase / Multiplicative Decrease (AIMD) concurrency controller.
    
    Dynamically tunes active worker count between min_workers and max_workers
    based on real-time segment download throughput, error rates, and latency.
    """

    def __init__(
        self,
        min_workers: int = 6,
        max_workers: int = 16,
        initial_workers: int = 12,
        window_size: int = 10,
    ):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self._current_workers = max(min_workers, min(max_workers, initial_workers))
        self.window_size = window_size

        self._lock = threading.RLock()
        self._recent_latencies: collections.deque = collections.deque(maxlen=50)
        self._recent_sizes: collections.deque = collections.deque(maxlen=50)
        self._window_durations: List[float] = []
        self._window_bytes: List[int] = []
        self._window_errors: int = 0
        self._prev_throughput_mb_s: float = 0.0

        self._total_success: int = 0
        self._total_failures: int = 0

    @property
    def current_workers(self) -> int:
        with self._lock:
            return self._current_workers

    def get_current_workers(self) -> int:
        return self.current_workers

    def record_success(self, duration: float, size_bytes: int) -> int:
        """Record a successful segment download and run AIMD adjustment if window is full."""
        with self._lock:
            self._total_success += 1
            self._recent_latencies.append(duration)
            self._recent_sizes.append(size_bytes)
            self._window_durations.append(duration)
            self._window_bytes.append(size_bytes)

            if len(self._window_durations) >= self.window_size:
                total_time = max(sum(self._window_durations), 0.001)
                total_mb = sum(self._window_bytes) / (1024 * 1024)
                avg_throughput = total_mb / (total_time / len(self._window_durations))

                # Additive Increase: If zero errors and throughput improved or stayed high
                if self._window_errors == 0:
                    if avg_throughput >= self._prev_throughput_mb_s * 0.95:
                        self._current_workers = min(self.max_workers, self._current_workers + 2)
                    elif avg_throughput < self._prev_throughput_mb_s * 0.70 and self._current_workers > self.min_workers:
                        # Slight decay if throughput degraded significantly despite no errors
                        self._current_workers = max(self.min_workers, self._current_workers - 1)
                else:
                    # Multiplicative Decrease: errors were encountered during the window
                    self._current_workers = max(self.min_workers, int(self._current_workers * 0.75))

                self._prev_throughput_mb_s = avg_throughput
                self._window_durations.clear()
                self._window_bytes.clear()
                self._window_errors = 0

            return self._current_workers

    def record_failure(self, status_code: int = 0) -> int:
        """Record a segment download failure and immediately backoff concurrency."""
        with self._lock:
            self._total_failures += 1
            self._window_errors += 1
            # Rate limit (429 or 420) immediately drops to min_workers
            if status_code in (420, 429):
                self._current_workers = self.min_workers
            else:
                # Multiplicative Decrease immediately on error / rate-limiting
                self._current_workers = max(self.min_workers, int(self._current_workers * 0.75))
            return self._current_workers

    def get_median_latency(self) -> float:
        """Return median latency in seconds of recent segment downloads (for hedging)."""
        with self._lock:
            if not self._recent_latencies:
                return 1.0
            sorted_lats = sorted(self._recent_latencies)
            mid = len(sorted_lats) // 2
            if len(sorted_lats) % 2 == 1:
                return sorted_lats[mid]
            return (sorted_lats[mid - 1] + sorted_lats[mid]) / 2.0

    def get_stats(self) -> Dict[str, Union[int, float]]:
        with self._lock:
            med_lat = self.get_median_latency()
            return {
                "current_workers": self._current_workers,
                "total_success": self._total_success,
                "total_failures": self._total_failures,
                "median_latency_s": round(med_lat, 3),
                "last_throughput_mb_s": round(self._prev_throughput_mb_s, 2),
            }


class SessionPool:
    """Thread-safe persistent HTTP session pool with Keep-Alive, retries, and metrics."""

    DEFAULT_HEADERS = {
        "Origin": "https://static.crunchyroll.com",
        "Referer": "https://static.crunchyroll.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }
    RATE_LIMIT_INITIAL_WAIT = 30.0
    MAX_RATE_LIMIT_WAIT = 300.0

    def _rate_limit_wait(self, response: requests.Response, retry_number: int) -> float:
        """Return a 30s, 60s, 120s... flood-wait delay for 420/429."""
        retry_after = response.headers.get("Retry-After", "")
        try:
            server_wait = float(retry_after)
        except (TypeError, ValueError):
            server_wait = 0.0
        scheduled_wait = self.RATE_LIMIT_INITIAL_WAIT * (2 ** max(retry_number - 1, 0))
        return min(max(scheduled_wait, server_wait), self.MAX_RATE_LIMIT_WAIT)

    def __init__(
        self,
        max_pool_size: int = 16,
        max_retries: int = 5,
        backoff_factor: float = 1.5,
        timeout: int = 20,
        config: Optional[ConcurrencyConfig] = None,
        rate_limit_gate: Optional[RateLimitGate] = None,
    ):
        self.config = config or ConcurrencyConfig(
            pool_size=max_pool_size,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            timeout=timeout,
        )
        self.max_pool_size = self.config.pool_size
        self.max_retries = self.config.max_retries
        self.backoff_factor = self.config.backoff_factor
        self.timeout = self.config.timeout
        self.rate_limit_gate = rate_limit_gate or RateLimitGate()

        self.scaler = AIMDConcurrencyScaler(
            min_workers=self.config.min_workers,
            max_workers=self.config.max_workers,
            initial_workers=self.config.initial_workers,
        )

        self._session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            # HTTP 420 and 429 are handled explicitly by the callers, which
            # report the cooldown and can honor Retry-After. Retrying them
            # here hides progress and can make API requests appear to hang.
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = TCPKeepAliveAdapter(
            pool_connections=self.max_pool_size,
            pool_maxsize=self.max_pool_size,
            max_retries=retry_strategy,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update(self.DEFAULT_HEADERS)

        self._closed = False
        self._lock = threading.Lock()

    def get_session(self) -> requests.Session:
        """Return the underlying requests.Session."""
        return self._session

    def get_recommended_workers(self) -> int:
        """Query current optimal worker concurrency from AIMD scaler."""
        if self.config.aimd_enabled:
            return self.scaler.get_current_workers()
        return self.config.initial_workers

    @staticmethod
    def _safe_url(url: str) -> str:
        """Return a diagnostic URL without query tokens or credentials."""
        parsed = urlsplit(url)
        return parsed.path or parsed.netloc or "<segment>"

    def download_segment(
        self,
        url: str,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        """Download a single media segment into bytes with retries and metrics tracking."""
        read_timeout = float(timeout) if timeout else float(self.timeout)
        t_out = (4.0, read_timeout)
        req_headers = dict(self.DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)

        attempt = 0
        last_exception: Optional[Exception] = None
        while attempt < self.max_retries:
            self.rate_limit_gate.wait_if_paused()
            start_t = time.time()
            attempt_number = attempt + 1
            try:
                with self._session.get(url, headers=req_headers, timeout=t_out) as resp:
                    duration = time.time() - start_t

                    if resp.status_code == 200:
                        data = resp.content
                        self.scaler.record_success(duration, len(data))
                        return data
                    if resp.status_code in (420, 429):
                        self.scaler.record_failure(resp.status_code)
                        last_exception = RuntimeError(
                            f"HTTP {resp.status_code} rate limit for {self._safe_url(url)}"
                        )
                        wait_time = self._rate_limit_wait(resp, attempt_number)
                        self.rate_limit_gate.trigger_pause(wait_time)
                        logger.warning(
                            "Rate limited downloading %s (HTTP %s, attempt %s/%s); "
                            "pausing all workers for %.1fs",
                            self._safe_url(url),
                            resp.status_code,
                            attempt_number,
                            self.max_retries,
                            wait_time,
                        )
                        if attempt < self.max_retries - 1:
                            self.rate_limit_gate.wait_if_paused()
                    elif 400 <= resp.status_code < 500:
                        self.scaler.record_failure(resp.status_code)
                        raise RuntimeError(
                            f"HTTP {resp.status_code} client error for {self._safe_url(url)}"
                        )
                    else:
                        self.scaler.record_failure(resp.status_code)
                        logger.warning(
                            "Transient HTTP %s downloading %s (attempt %s/%s)",
                            resp.status_code,
                            self._safe_url(url),
                            attempt_number,
                            self.max_retries,
                        )
                        if attempt < self.max_retries - 1:
                            time.sleep(min(1.0, self.backoff_factor * max(1, attempt_number)))
            except RuntimeError:
                # Preserve non-retryable HTTP errors instead of retrying and
                # replacing the useful status with a generic final exception.
                raise
            except Exception as e:
                last_exception = e
                duration = time.time() - start_t
                self.scaler.record_failure(0)
                logger.warning(
                    "Segment request failed for %s (attempt %s/%s, %.1fs): %s: %s",
                    self._safe_url(url),
                    attempt_number,
                    self.max_retries,
                    duration,
                    type(e).__name__,
                    e,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(min(1.0, self.backoff_factor * max(1, attempt_number)))

            attempt += 1

        err_msg = (
            f"Failed to download segment after {self.max_retries} attempts: "
            f"{self._safe_url(url)}"
        )
        if last_exception:
            err_msg += f" (Last error: {last_exception})"
        raise RuntimeError(err_msg)

    def download_segment_stream(
        self,
        url: str,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        chunk_size: Optional[int] = None,
    ) -> Generator[bytes, None, None]:
        """Stream a media segment chunk by chunk."""
        self.rate_limit_gate.wait_if_paused()
        read_timeout = float(timeout) if timeout else float(self.timeout)
        t_out = (4.0, read_timeout)
        c_size = chunk_size or self.config.chunk_size
        req_headers = dict(self.DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)

        start_t = time.time()
        total_size = 0
        try:
            with self._session.get(url, headers=req_headers, stream=True, timeout=t_out) as resp:
                if resp.status_code in (420, 429):
                    self.scaler.record_failure(resp.status_code)
                    wait_time = self._rate_limit_wait(resp, 1)
                    self.rate_limit_gate.trigger_pause(wait_time)
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=c_size):
                    if chunk:
                        total_size += len(chunk)
                        yield chunk
            duration = time.time() - start_t
            self.scaler.record_success(duration, total_size)
        except Exception as e:
            self.scaler.record_failure(0)
            raise e

    def download_file_stream(
        self,
        url: str,
        output_path: str,
        timeout: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        chunk_size: Optional[int] = None,
        progress_callback=None,
        parallel_ranges: int = 8,
        range_size: int = 4 * 1024 * 1024,
    ) -> int:
        """Stream a complete media file to disk and reject truncated responses.

        ``progress_callback`` receives ``(written_bytes, expected_bytes,
        speed_mb_s)`` periodically and once more when the response completes.
        ``expected_bytes`` is zero when the server does not provide a numeric
        Content-Length.
        """
        # Use a separate read timeout so a CDN that stops sending bytes cannot
        # leave the complete-file branch waiting indefinitely.
        t_out = (10, timeout or self.timeout)
        c_size = chunk_size or self.config.chunk_size
        req_headers = dict(self.DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)

        if parallel_ranges > 1:
            ranged_size = self._download_file_ranges(
                url,
                output_path,
                t_out,
                req_headers,
                c_size,
                parallel_ranges,
                range_size,
                progress_callback,
            )
            if ranged_size is not None:
                return ranged_size

        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self.rate_limit_gate.wait_if_paused()
            started = time.time()
            last_progress = started
            written = 0
            expected_bytes: Optional[int] = None
            try:
                with self._session.get(
                    url, headers=req_headers, stream=True, timeout=t_out
                ) as resp:
                    if resp.status_code in (420, 429):
                        self.scaler.record_failure(resp.status_code)
                        wait_time = self._rate_limit_wait(resp, attempt + 1)
                        self.rate_limit_gate.trigger_pause(wait_time)
                        if attempt < self.max_retries - 1:
                            self.rate_limit_gate.wait_if_paused()
                            continue
                        resp.raise_for_status()

                    if 400 <= resp.status_code < 500:
                        self.scaler.record_failure(resp.status_code)
                        raise RuntimeError(
                            f"HTTP {resp.status_code} client error for {self._safe_url(url)}"
                        )
                    resp.raise_for_status()
                    expected = resp.headers.get("Content-Length")
                    expected_bytes = int(expected) if expected and expected.isdigit() else None
                    with open(output_path, "wb", buffering=1024 * 1024) as output:
                        for chunk in resp.iter_content(chunk_size=c_size):
                            if chunk:
                                output.write(chunk)
                                written += len(chunk)
                                now = time.time()
                                if now - last_progress >= 1:
                                    elapsed = max(now - started, 0.001)
                                    if progress_callback:
                                        progress_callback(
                                            written,
                                            expected_bytes or 0,
                                            written / elapsed / (1024 * 1024),
                                        )
                                    logger.info(
                                        "Complete-file download progress for %s: %s bytes received%s",
                                        self._safe_url(url),
                                        written,
                                        f" of {expected_bytes}" if expected_bytes is not None else "",
                                    )
                                    last_progress = now

                if expected_bytes is not None and written != expected_bytes:
                    raise IOError(
                        f"truncated response: received {written} of {expected_bytes} bytes"
                    )
                if progress_callback:
                    elapsed = max(time.time() - started, 0.001)
                    progress_callback(
                        written,
                        expected_bytes or 0,
                        written / elapsed / (1024 * 1024),
                    )
                self.scaler.record_success(time.time() - started, written)
                return written
            except RuntimeError:
                # Preserve useful non-retryable client errors, matching the
                # behavior of download_segment().
                raise
            except Exception as exc:
                last_exception = exc
                self.scaler.record_failure(0)
                logger.warning(
                    "Complete-file download failed for %s (attempt %s/%s): %s: %s",
                    self._safe_url(url),
                    attempt + 1,
                    self.max_retries,
                    type(exc).__name__,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_factor * max(1, attempt + 1))

        raise RuntimeError(
            f"Failed to download complete media file after {self.max_retries} attempts: "
            f"{self._safe_url(url)} ({last_exception})"
        )

    def _download_file_ranges(
        self,
        url: str,
        output_path: str,
        timeout: Tuple[int, int],
        headers: Dict[str, str],
        chunk_size: int,
        worker_count: int,
        range_size: int,
        progress_callback,
    ) -> Optional[int]:
        """Download a complete file using concurrent byte ranges when supported."""
        probe_headers = dict(headers)
        probe_headers["Range"] = "bytes=0-0"
        probe_headers["Accept-Encoding"] = "identity"
        try:
            with self._session.get(url, headers=probe_headers, stream=True, timeout=timeout) as probe:
                if probe.status_code != 206:
                    return None
                content_range = probe.headers.get("Content-Range", "")
                total_text = content_range.rsplit("/", 1)[-1] if "/" in content_range else ""
                total_size = int(total_text) if total_text.isdigit() else 0
                if total_size <= 0:
                    return None
        except Exception:
            # The normal downloader below has its own retry and error handling.
            return None

        ranges = [
            (start, min(start + range_size - 1, total_size - 1))
            for start in range(0, total_size, range_size)
        ]
        progress_lock = threading.Lock()
        completed = 0
        started = time.time()
        last_report = 0.0

        def download_range(byte_range):
            start, end = byte_range
            range_headers = dict(headers)
            range_headers["Range"] = f"bytes={start}-{end}"
            range_headers["Accept-Encoding"] = "identity"
            last_error = None
            # A range request is only an optimization. Keep its failure
            # window short so a throttled CDN can fall back to the validated
            # sequential downloader instead of appearing hung for minutes.
            range_retries = min(self.max_retries, 3)
            range_timeout = (timeout[0], min(timeout[1], 10))
            for attempt in range(range_retries):
                self.rate_limit_gate.wait_if_paused()
                range_started = time.time()
                try:
                    with self._session.get(
                        url, headers=range_headers, stream=True, timeout=range_timeout
                    ) as response:
                        if response.status_code in (420, 429):
                            wait_time = self._rate_limit_wait(response, attempt + 1)
                            self.rate_limit_gate.trigger_pause(wait_time)
                            if attempt < range_retries - 1:
                                self.rate_limit_gate.wait_if_paused()
                            continue
                        if response.status_code != 206:
                            raise RuntimeError(
                                f"HTTP {response.status_code} range response for {self._safe_url(url)}"
                            )
                        data = b"".join(response.iter_content(chunk_size=chunk_size))
                        expected = end - start + 1
                        if len(data) != expected:
                            raise IOError(
                                f"short range: received {len(data)} of {expected} bytes"
                            )
                        range_elapsed = max(time.time() - range_started, 0.001)
                        logger.info(
                            "Completed media range %s-%s for %s in %.1fs (%.2f MB/s)",
                            start,
                            end,
                            self._safe_url(url),
                            range_elapsed,
                            len(data) / range_elapsed / (1024 * 1024),
                        )
                        return start, data
                except Exception as exc:
                    last_error = exc
                    if attempt < range_retries - 1:
                        time.sleep(self.backoff_factor * max(1, attempt + 1))
            raise RuntimeError(
                f"Failed byte range {start}-{end} after {range_retries} attempts: {last_error}"
            )

        try:
            with open(output_path, "wb") as output:
                output.truncate(total_size)
                executor = ThreadPoolExecutor(max_workers=min(worker_count, len(ranges)))
                futures = [executor.submit(download_range, item) for item in ranges]
                try:
                    pending = set(futures)
                    while pending:
                        done, pending = wait(
                            pending, timeout=2.0, return_when=FIRST_COMPLETED
                        )
                        now = time.time()
                        if not done:
                            if progress_callback:
                                elapsed = max(now - started, 0.001)
                                progress_callback(
                                    completed,
                                    total_size,
                                    completed / elapsed / (1024 * 1024),
                                )
                            continue
                        for future in done:
                            start, data = future.result()
                            output.seek(start)
                            output.write(data)
                            with progress_lock:
                                completed += len(data)
                                now = time.time()
                                if progress_callback and (now - last_report >= 0.5 or completed == total_size):
                                    elapsed = max(now - started, 0.001)
                                    progress_callback(
                                        completed,
                                        total_size,
                                        completed / elapsed / (1024 * 1024),
                                    )
                                    last_report = now
                except Exception:
                    for future in futures:
                        future.cancel()
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                else:
                    executor.shutdown(wait=True)
            self.scaler.record_success(time.time() - started, total_size)
            return total_size
        except Exception:
            try:
                with open(output_path, "wb"):
                    pass
            except OSError:
                pass
            # Returning None lets download_file_stream() retry the complete
            # file sequentially, which is safer than exposing a partial range
            # batch to callers.
            return None

    def download_segment_hedged(
        self,
        url: str,
        timeout: Optional[int] = None,
        hedge_delay: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        """Download a segment with tail-latency hedging against slow CDN stragglers."""
        if not self.config.hedging_enabled:
            return self.download_segment(url, timeout=timeout, headers=headers)

        t_out = timeout or self.timeout
        delay = hedge_delay
        if delay is None:
            med_lat = self.scaler.get_median_latency()
            delay = max(self.config.hedge_min_delay, med_lat * self.config.hedge_factor)

        res_queue: queue.Queue = queue.Queue(maxsize=2)
        stop_event = threading.Event()

        def _worker(worker_id: int):
            try:
                data = self.download_segment(url, timeout=t_out, headers=headers)
                if not stop_event.is_set():
                    res_queue.put(("ok", data, worker_id))
            except Exception as e:
                if not stop_event.is_set():
                    res_queue.put(("err", e, worker_id))

        # Start primary request
        t1 = threading.Thread(target=_worker, args=(1,), daemon=True)
        t1.start()

        # Wait up to hedge_delay for primary to finish
        try:
            status, val, _ = res_queue.get(timeout=delay)
            if status == "ok":
                stop_event.set()
                return val
        except queue.Empty:
            # Primary is lagging; launch speculative secondary request
            t2 = threading.Thread(target=_worker, args=(2,), daemon=True)
            t2.start()

        # Wait for either worker to complete
        remaining_timeout = max(1.0, float(t_out) - delay)
        try:
            status, val, _ = res_queue.get(timeout=remaining_timeout)
            if status == "ok":
                stop_event.set()
                return val
            else:
                # If first resulted in error, try waiting briefly for the other worker
                try:
                    status2, val2, _ = res_queue.get(timeout=min(remaining_timeout, 3.0))
                    if status2 == "ok":
                        stop_event.set()
                        return val2
                except queue.Empty:
                    pass
                stop_event.set()
                raise val
        except queue.Empty:
            stop_event.set()
            raise TimeoutError(f"Hedged segment download timed out for {url}")

    def close(self):
        """Close the underlying session and free connections."""
        with self._lock:
            if not self._closed:
                self._session.close()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
