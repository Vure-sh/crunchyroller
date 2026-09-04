import time
import threading
import requests
from typing import Optional
from urllib.parse import urlparse
from urllib3.util import Timeout as Urllib3Timeout
from .auth import get_access_token, login_with_credentials, load_config, save_config
from .session_pool import SessionPool, ConcurrencyConfig, RateLimitGate


class CrunchyrollHttpClient:
    DEFAULT_REQUEST_TIMEOUT = 20
    MAX_REQUEST_WALL_TIME = 90
    HEARTBEAT_INTERVAL = 15
    MAX_RATE_LIMIT_RETRIES = 10
    RATE_LIMIT_INITIAL_WAIT = 30
    MAX_RATE_LIMIT_WAIT = 300

    def __init__(
        self,
        etp_rt: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        session_pool: Optional[SessionPool] = None,
    ):
        self.etp_rt = etp_rt or ""
        self.username = username
        self.password = password
        self.token = ""

        self.session_pool = session_pool or SessionPool(
            config=ConcurrencyConfig(
                pool_size=16,
                min_workers=4,
                max_workers=8,
                initial_workers=6,
                max_retries=5,
                backoff_factor=1.5,
                timeout=20,
            )
        )
        self.session = self.session_pool.get_session()
        self.rate_limit_gate = getattr(self.session_pool, "rate_limit_gate", None) or RateLimitGate()

        # check for android tv tokens
        cfg = load_config()
        self.android_token = cfg.get("android_access_token", "")
        self.android_refresh_token = cfg.get("android_refresh_token", "")

        # try to load etp_rt from config
        if not self.etp_rt:
            if "etp_rt" in cfg and cfg["etp_rt"]:
                self.etp_rt = cfg["etp_rt"]

        # username & password provided? log in directly via Android TV client
        if self.username and self.password:
            try:
                acc_tok, ref_tok = login_with_credentials(self.username, self.password)
                self.android_token = acc_tok
                self.android_refresh_token = ref_tok
                self.token = acc_tok
                save_config({"username": self.username})
            except Exception as e:
                print(f"[auth] Android TV credentials login failed: {e}")

        # prioritize Android TV token if available
        if self.android_token:
            self.token = self.android_token
        elif self.android_refresh_token:
            self.refresh_android_token()
        elif self.etp_rt:
            try:
                self.token = get_access_token(self.etp_rt)
            except Exception as e:
                print(f"[auth] Failed to refresh web token from etp_rt: {e}")

    def refresh_token(self) -> None:
        if self.android_refresh_token:
            self.refresh_android_token()
        elif self.etp_rt:
            try:
                self.token = get_access_token(self.etp_rt)
            except Exception as e:
                print(f"[auth] Failed to refresh web token from etp_rt: {e}")

    def refresh_android_token(self) -> None:
        if self.android_refresh_token:
            from .auth import refresh_android_tv_token
            try:
                new_acc, new_ref = refresh_android_tv_token(self.android_refresh_token)
                self.android_token = new_acc
                self.android_refresh_token = new_ref
                self.token = new_acc
            except Exception as e:
                print(f"[auth] Failed to refresh Android TV token: {e}")

    def _rate_limit_wait(self, response: requests.Response, retry_number: int) -> int:
        """Return a flood-wait-aware delay for a 420/429 response."""
        retry_after = response.headers.get("Retry-After", "")
        try:
            requested_wait = int(retry_after)
        except (TypeError, ValueError):
            requested_wait = 0

        scheduled_wait = self.RATE_LIMIT_INITIAL_WAIT * (2 ** max(retry_number - 1, 0))
        if requested_wait > 0:
            scheduled_wait = max(scheduled_wait, requested_wait)

        # Cap each sleep while retaining the increasing flood-wait signal.
        return min(scheduled_wait, self.MAX_RATE_LIMIT_WAIT)

    def do_request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        requested_timeout = kwargs.pop("timeout", self.DEFAULT_REQUEST_TIMEOUT)
        try:
            requested_timeout = float(requested_timeout)
        except (TypeError, ValueError):
            requested_timeout = float(self.DEFAULT_REQUEST_TIMEOUT)
        # A read timeout is inactivity-based and can be reset repeatedly by a
        # slow server. urllib3's total timeout adds a real wall-clock bound.
        request_timeout = Urllib3Timeout(
            connect=min(10.0, requested_timeout),
            read=requested_timeout,
            total=max(requested_timeout, float(self.MAX_REQUEST_WALL_TIME)),
        )
        kwargs["timeout"] = request_timeout
        if "Authorization" not in headers and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if "User-Agent" not in headers:
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"

        request_started = time.monotonic()
        request_path = urlparse(url).path or "/"
        heartbeat_stop = threading.Event()

        def _heartbeat() -> None:
            while not heartbeat_stop.wait(self.HEARTBEAT_INTERVAL):
                elapsed = time.monotonic() - request_started
                print(
                    f"[http] Still waiting: {method.upper()} {request_path} "
                    f"({elapsed:.0f}s elapsed; wall-clock deadline="
                    f"{self.MAX_REQUEST_WALL_TIME}s)...",
                    flush=True,
                )

        print(
            f"[http] Dispatching {method.upper()} {request_path} "
            f"(timeout={requested_timeout:g}s, wall={self.MAX_REQUEST_WALL_TIME}s)...",
            flush=True,
        )
        heartbeat = threading.Thread(target=_heartbeat, daemon=True)
        heartbeat.start()
        if hasattr(self, "rate_limit_gate") and self.rate_limit_gate:
            self.rate_limit_gate.wait_if_paused()
        try:
            response = self.session.request(method, url, headers=headers, **kwargs)
        except Exception as exc:
            elapsed = time.monotonic() - request_started
            print(
                f"[http] Request failed: {method.upper()} {request_path} "
                f"after {elapsed:.1f}s: {type(exc).__name__}: {exc}",
                flush=True,
            )
            raise
        finally:
            heartbeat_stop.set()

        elapsed = time.monotonic() - request_started
        print(
            f"[http] Response: {method.upper()} {request_path} "
            f"HTTP {response.status_code} after {elapsed:.1f}s",
            flush=True,
        )
        if response.status_code == 401:
            print("[http] Access token expired; refreshing and retrying request...", flush=True)
            if self.android_refresh_token:
                self.refresh_android_token()
                if self.android_token:
                    headers["Authorization"] = f"Bearer {self.android_token}"
            elif self.etp_rt:
                self.refresh_token()
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"
            retry_started = time.monotonic()
            try:
                response = self.session.request(method, url, headers=headers, **kwargs)
            except Exception as exc:
                elapsed = time.monotonic() - retry_started
                print(
                    f"[http] Refreshed-token retry failed for {method.upper()} {request_path} "
                    f"after {elapsed:.1f}s: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                raise
            print(
                f"[http] Refreshed-token retry response: HTTP {response.status_code} "
                f"after {time.monotonic() - retry_started:.1f}s",
                flush=True,
            )

        retries = 0
        while response.status_code in {420, 429} and retries < self.MAX_RATE_LIMIT_RETRIES:
            retries += 1
            status_code = response.status_code
            wait_time = self._rate_limit_wait(response, retries)
            if hasattr(self, "rate_limit_gate") and self.rate_limit_gate:
                self.rate_limit_gate.trigger_pause(wait_time)
            retry_after = response.headers.get("Retry-After", "")
            header_note = f" Retry-After={retry_after}s." if retry_after else ""
            print(
                f"[http] Rate limited by Crunchyroll ({status_code}). "
                f"Waiting {wait_time} seconds before retry "
                f"({retries}/{self.MAX_RATE_LIMIT_RETRIES}).{header_note}",
                flush=True,
            )
            if hasattr(self, "rate_limit_gate") and self.rate_limit_gate:
                self.rate_limit_gate.wait_if_paused()
            else:
                time.sleep(wait_time)
            retry_started = time.monotonic()
            response = self.session.request(method, url, headers=headers, **kwargs)
            print(
                f"[http] Rate-limit retry response: HTTP {response.status_code} "
                f"after {time.monotonic() - retry_started:.1f}s",
                flush=True,
            )

        return response

    def close(self):
        if self.session_pool:
            self.session_pool.close()
