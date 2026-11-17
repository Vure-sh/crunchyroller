import json
import os
import time
import uuid
from typing import Dict, Any, Optional, Tuple
import requests

import threading
import shutil

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")
CONFIG_LOCK = threading.RLock()

DEFAULT_CONFIG: Dict[str, Any] = {
    "video_quality": "1080p",
    "audio_quality": "192k",
    "audio_lang": "ja-JP",
    "subs_lang": "en-US",
    "force_download": False,
    "enable_logging": True,
    "audio_fallback": True,
}


def _find_fallback_config() -> Optional[str]:
    """Look for an existing non-empty config.json in parent directory if current is missing."""
    parent_dir = os.path.dirname(_PROJECT_ROOT)
    candidate_dirs = [
        parent_dir,
    ]
    for c_dir in candidate_dirs:
        c_path = os.path.join(c_dir, "config.json")
        if c_path != CONFIG_FILE and os.path.isfile(c_path):
            try:
                if os.path.getsize(c_path) > 10:
                    with open(c_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and (data.get("etp_rt") or data.get("username") or data.get("android_access_token")):
                        return c_path
            except Exception:
                continue
    return None


def save_config(config_dict: Dict[str, Any], config_path: Optional[str] = None) -> None:
    """Safely and atomically update settings in config.json without losing existing keys."""
    target_path = config_path or CONFIG_FILE
    with CONFIG_LOCK:
        existing: Dict[str, Any] = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        loaded = json.loads(content)
                        if isinstance(loaded, dict):
                            existing = loaded
            except Exception as e:
                # If file exists but is unparseable, NEVER overwrite/truncate it with empty dict!
                print(f"[config] Warning: Failed to parse existing {target_path} ({e}); backing up before rewrite.")
                try:
                    import time
                    bak_path = f"{target_path}.bak.{int(time.time())}"
                    shutil.copy2(target_path, bak_path)
                except Exception:
                    pass

        # Update existing keys without wiping unmentioned keys
        # Passing None for a key safely deletes it from config
        for k, v in config_dict.items():
            if v is None:
                existing.pop(k, None)
            else:
                existing[k] = v

        # Atomic write via temporary file in the same directory + os.replace
        dir_name = os.path.dirname(os.path.abspath(target_path)) or "."
        base_name = os.path.basename(target_path)
        temp_path = os.path.join(dir_name, f".{base_name}.tmp.{os.getpid()}")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, target_path)
        except Exception as e:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except Exception: pass
            print(f"[config] Warning: Failed to save config to {target_path}: {e}")


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load config from disk. If file does not exist, initialize it safely."""
    target_path = config_path or CONFIG_FILE
    with CONFIG_LOCK:
        if not os.path.exists(target_path):
            # Check for existing fallback config to inherit
            fallback = _find_fallback_config()
            if fallback and os.path.isfile(fallback):
                try:
                    with open(fallback, "r", encoding="utf-8") as f:
                        inherited = json.load(f)
                    if isinstance(inherited, dict) and inherited:
                        save_config(inherited, target_path)
                        return dict(inherited)
                except Exception:
                    pass

            try:
                save_config(DEFAULT_CONFIG, target_path)
                return dict(DEFAULT_CONFIG)
            except Exception:
                return dict(DEFAULT_CONFIG)

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return dict(DEFAULT_CONFIG)
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
                return dict(DEFAULT_CONFIG)
        except Exception as e:
            print(f"[config] Warning: Error reading {target_path}: {e}")
            return dict(DEFAULT_CONFIG)


def get_device_id(config_path: Optional[str] = None) -> str:
    """Retrieve the persistent device ID from config or generate and save a new one."""
    target_path = config_path or CONFIG_FILE
    cfg = load_config(target_path)
    dev_id = cfg.get("device_id")
    if dev_id and isinstance(dev_id, str) and dev_id.strip():
        return dev_id.strip()
    new_id = str(uuid.uuid4())
    save_config({"device_id": new_id}, target_path)
    return new_id


def _get_device_id_val() -> str:
    try:
        return get_device_id()
    except Exception:
        return str(uuid.uuid4())


_DEVICE_ID = _get_device_id_val()

_TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}
_TOKEN_CACHE_LOCK = threading.Lock()


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    """Safely decode and return JWT claims payload dictionary."""
    if not token or not isinstance(token, str):
        return {}
    parts = token.split(".")
    if len(parts) >= 2:
        try:
            import base64
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
            return json.loads(payload_bytes.decode("utf-8", errors="replace"))
        except Exception:
            pass
    return {}


def is_jwt_expired(token: Optional[str], buffer_seconds: int = 60) -> bool:
    """Check if a JWT token is expired or within buffer_seconds of expiration."""
    if not token or not str(token).strip():
        return True
    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    if exp is not None:
        return (time.time() + buffer_seconds) >= float(exp)
    return False


def _extract_account_id(access_token: str) -> Optional[str]:
    """Helper to extract account ID from a Crunchyroll bearer token."""
    claims = decode_jwt_payload(access_token)
    return (
        claims.get("account_id")
        or claims.get("etp_user_id")
        or (claims.get("scopes", {}).get("cr", {}).get("acc_id"))
        or claims.get("sub")
    )


def validate_profile_pin(account_id: str, profile_id: str, pin: str, access_token: str) -> str:
    """Validate a profile PIN with Crunchyroll and obtain a CrPassToken."""
    url = f"https://www.crunchyroll.com/auth/v1/{account_id}/passtoken"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }
    payload = {
        "credential_type": "profile_pin",
        "profile_id": profile_id,
        "value": str(pin).strip(),
    }
    res = requests.post(url, headers=headers, json=payload, timeout=15)
    if res.status_code == 200:
        data = res.json()
        return data.get("code", "")
    elif res.status_code == 401:
        raise ValueError("Invalid profile PIN")
    else:
        raise RuntimeError(f"PIN validation failed ({res.status_code}): {res.text}")


def get_access_token(
    etp_rt: str,
    profile_id: Optional[str] = None,
    pass_token: Optional[str] = None,
    force_refresh: bool = False,
) -> str:
    """Swap session cookie / refresh token for a bearer token, scoped to profile if specified."""
    now = time.time()
    explicit_pid = bool(profile_id and str(profile_id).strip())
    target_pid = (profile_id or "").strip()
    if not target_pid:
        try:
            cfg = load_config()
            target_pid = (cfg.get("selected_profile_id") or "").strip()
        except Exception:
            pass

    cache_key = f"{etp_rt}:{target_pid}" if target_pid else etp_rt
    with _TOKEN_CACHE_LOCK:
        if not force_refresh and cache_key in _TOKEN_CACHE:
            cached_token, expire_at = _TOKEN_CACHE[cache_key]
            if now < expire_at:
                return cached_token

    dev_id = get_device_id()
    url = "https://www.crunchyroll.com/auth/v1/token"
    headers = {
        "Authorization": "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }

    # If target profile specified but no pass_token passed, check if a PIN was remembered in config
    if target_pid and not pass_token:
        try:
            cfg = load_config()
            saved_pins = dict(cfg.get("saved_profile_pins") or {})
            saved_pin = saved_pins.get(target_pid)
            if saved_pin:
                acc_tok = None
                with _TOKEN_CACHE_LOCK:
                    cached_acc = _TOKEN_CACHE.get(etp_rt)
                    if cached_acc and not is_jwt_expired(cached_acc[0]):
                        acc_tok = cached_acc[0]
                if not acc_tok:
                    d_acc = {"grant_type": "etp_rt_cookie", "device_id": dev_id, "device_type": "Chrome on Windows"}
                    r_acc = requests.post(url, headers=headers, cookies={"device_id": dev_id, "etp_rt": etp_rt}, data=d_acc, timeout=15)
                    if r_acc.status_code == 200:
                        acc_tok = r_acc.json().get("access_token", "")
                        with _TOKEN_CACHE_LOCK:
                            _TOKEN_CACHE[etp_rt] = (acc_tok, now + 270)
                if acc_tok:
                    aid = _extract_account_id(acc_tok)
                    if aid:
                        try:
                            pass_token = validate_profile_pin(aid, target_pid, saved_pin, acc_tok)
                        except Exception:
                            # Stale saved PIN: purge immediately
                            saved_pins.pop(target_pid, None)
                            save_config({"saved_profile_pins": saved_pins})
        except Exception:
            pass

    if pass_token:
        headers["CrPassToken"] = pass_token

    cookies = {
        "device_id": dev_id,
        "etp_rt": etp_rt,
    }
    if target_pid:
        data = {
            "grant_type": "refresh_token_profile_id",
            "refresh_token": etp_rt,
            "profile_id": target_pid,
            "device_id": dev_id,
            "device_type": "Chrome on Windows",
            "scope": "offline_access",
        }
    else:
        data = {
            "grant_type": "etp_rt_cookie",
            "device_id": dev_id,
            "device_type": "Chrome on Windows",
        }

    response = requests.post(url, headers=headers, cookies=cookies, data=data, timeout=20)
    if response.status_code != 200:
        # If profile-specific token refresh failed without a pass_token, fallback to account-level cookie grant
        if target_pid and not pass_token:
            data_fallback = {
                "grant_type": "etp_rt_cookie",
                "device_id": dev_id,
                "device_type": "Chrome on Windows",
            }
            fb_resp = requests.post(url, headers={"Authorization": headers["Authorization"], "Content-Type": headers["Content-Type"], "User-Agent": headers["User-Agent"]}, cookies=cookies, data=data_fallback, timeout=20)
            if fb_resp.status_code == 200:
                json_resp = fb_resp.json()
                token = json_resp.get("access_token", "")
                expires_in = int(json_resp.get("expires_in", 300))
                with _TOKEN_CACHE_LOCK:
                    _TOKEN_CACHE[etp_rt] = (token, now + max(10, expires_in - 30))
                if explicit_pid:
                    # Profile switch itself failed (e.g. PIN required), raise so caller knows
                    raise RuntimeError(
                        f"Profile switch failed (status {response.status_code}): {response.text}"
                    )
                # Saved profile was PIN protected; return fallback account token so app stays authenticated
                return token
        raise RuntimeError(
            f"Failed to get access token (status {response.status_code}): {response.text}"
        )

    json_resp = response.json()
    token = json_resp.get("access_token", "")
    expires_in = int(json_resp.get("expires_in", 300))
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[cache_key] = (token, now + max(10, expires_in - 30))
        if cache_key != etp_rt:
            _TOKEN_CACHE[etp_rt] = (token, now + max(10, expires_in - 30))
    return token


def switch_profile(
    etp_rt: str,
    profile_id: str,
    pin: Optional[str] = None,
    account_id: Optional[str] = None,
    remember_pin: bool = False,
) -> str:
    """Switch active profile, validating PIN if protected, and persisting selection and PIN in config."""
    cfg = load_config()
    saved_pins = dict(cfg.get("saved_profile_pins") or {})
    pass_token = None

    clean_pin = str(pin).strip() if (pin and str(pin).strip()) else None
    effective_pin = clean_pin or saved_pins.get(profile_id)

    if effective_pin:
        curr_token = get_access_token(etp_rt)
        target_aid = (account_id or "").strip() or _extract_account_id(curr_token)
        if target_aid:
            try:
                pass_token = validate_profile_pin(target_aid, profile_id, effective_pin, curr_token)
            except ValueError as ve:
                # Invalid PIN (e.g. user changed it on Crunchyroll): purge remembered PIN immediately
                if profile_id in saved_pins:
                    saved_pins.pop(profile_id, None)
                    save_config({"saved_profile_pins": saved_pins})
                raise ValueError("Invalid profile PIN") from ve

    try:
        token = get_access_token(etp_rt, profile_id=profile_id, pass_token=pass_token, force_refresh=True)
        updates: Dict[str, Any] = {"selected_profile_id": profile_id}
        if clean_pin and remember_pin:
            saved_pins[profile_id] = clean_pin
            updates["saved_profile_pins"] = saved_pins
        elif clean_pin and not remember_pin:
            # If user explicitly provided a pin without remember, clear any previously saved pin
            if profile_id in saved_pins:
                saved_pins.pop(profile_id, None)
                updates["saved_profile_pins"] = saved_pins
        save_config(updates)
        return token
    except Exception as e:
        err_str = str(e)
        if "invalid_grant" in err_str or "invalid_credentials" in err_str:
            if profile_id in saved_pins:
                saved_pins.pop(profile_id, None)
                save_config({"saved_profile_pins": saved_pins})
            raise PermissionError("PIN_REQUIRED")
        raise


def get_guest_token(force_refresh: bool = False) -> str:
    """Fetch an anonymous client_credentials bearer token for public catalog browsing & search."""
    now = time.time()
    with _TOKEN_CACHE_LOCK:
        if not force_refresh and "guest" in _TOKEN_CACHE:
            cached_token, expire_at = _TOKEN_CACHE["guest"]
            if now < expire_at:
                return cached_token

    url = "https://www.crunchyroll.com/auth/v1/token"
    headers = {
        "Authorization": "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }
    data = {
        "grant_type": "client_credentials",
    }

    try:
        response = requests.post(url, headers=headers, data=data, timeout=20)
        if response.status_code != 200:
            # Fallback to Android TV client credentials
            url_android = "https://beta-api.crunchyroll.com/auth/v1/token"
            headers_android = {
                "Authorization": ANDROID_BASIC_AUTH,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": ANDROID_USER_AGENT,
            }
            response = requests.post(url_android, headers=headers_android, data=data, timeout=20)
    except Exception as exc:
        raise RuntimeError(f"Failed to obtain guest token: {exc}")

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to get guest token (status {response.status_code}): {response.text}"
        )

    json_resp = response.json()
    token = json_resp.get("access_token", "")
    expires_in = int(json_resp.get("expires_in", 300))
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE["guest"] = (token, now + max(10, expires_in - 30))
    return token

ANDROID_BASIC_AUTH = "Basic ZXZ4YzVybGN1bnd4cm91YWpmeHI6NkJGWGM1SUk3UWx2Z3NFbzdiVjBuWUNfN1VRLXVlSVM="
ANDROID_CLIENT_ID = "evxc5rlcunwxrouajfxr"
ANDROID_CLIENT_SECRET = "6BFXc5II7QlvgsEo7bV0nYC_7UQ-ueIS"
ANDROID_USER_AGENT = "Crunchyroll/ANDROIDTV/3.70.0_22358 (Android 12; en-US; SHIELD Android TV Build/SR1A.220624.014)"


def login_with_android_tv(
    username: str, password: str, device_id: Optional[str] = None
) -> Tuple[str, str]:
    """Authenticates using Crunchyroll's official Android TV client credentials.
    Returns (access_token, refresh_token).
    """
    dev_id = device_id or get_device_id()
    url = "https://beta-api.crunchyroll.com/auth/v1/token"
    headers = {
        "User-Agent": ANDROID_USER_AGENT,
        "Authorization": ANDROID_BASIC_AUTH,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "ETP-Anonymous-ID": dev_id,
        "Request-Type": "SignIn",
    }
    data = {
        "username": username,
        "password": password,
        "grant_type": "password",
        "scope": "offline_access",
        "client_id": ANDROID_CLIENT_ID,
        "client_secret": ANDROID_CLIENT_SECRET,
        "device_id": dev_id,
        "device_name": "SHIELD Android TV",
        "device_type": "ANDROIDTV",
    }
    resp = requests.post(url, headers=headers, data=data, timeout=20)
    if resp.status_code != 200:
        error_msg = resp.text
        try:
            err_json = resp.json()
            error_msg = (
                err_json.get("error_description")
                or err_json.get("error")
                or err_json.get("message")
                or error_msg
            )
        except Exception:
            pass
        raise RuntimeError(f"Android TV login failed ({resp.status_code}): {error_msg}")

    body = resp.json()
    access_token = body.get("access_token", "")
    refresh_token = body.get("refresh_token", "")
    if not access_token:
        raise RuntimeError("No access_token returned by Android TV login.")

    save_config({
        "android_access_token": access_token,
        "android_refresh_token": refresh_token,
        "username": username,
        "device_id": dev_id,
    })
    return access_token, refresh_token


def refresh_android_tv_token(
    refresh_token: str, device_id: Optional[str] = None
) -> Tuple[str, str]:
    """Refreshes an expired Android TV access token.
    Returns (new_access_token, new_refresh_token).
    """
    dev_id = device_id or get_device_id()
    url = "https://beta-api.crunchyroll.com/auth/v1/token"
    headers = {
        "User-Agent": ANDROID_USER_AGENT,
        "Authorization": ANDROID_BASIC_AUTH,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "offline_access",
        "client_id": ANDROID_CLIENT_ID,
        "client_secret": ANDROID_CLIENT_SECRET,
        "device_id": dev_id,
        "device_type": "ANDROIDTV",
    }
    resp = requests.post(url, headers=headers, data=data, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to refresh Android TV token ({resp.status_code}): {resp.text}")

    body = resp.json()
    new_access = body.get("access_token", "")
    new_refresh = body.get("refresh_token", refresh_token)
    save_config({
        "android_access_token": new_access,
        "android_refresh_token": new_refresh,
        "device_id": dev_id,
    })
    return new_access, new_refresh


def login_with_credentials(
    username: str, password: str, device_id_val: Optional[str] = None
) -> Tuple[str, str]:
    """Login with username & password using Android TV client to get native Android TV tokens."""
    return login_with_android_tv(username, password, device_id=device_id_val)
