import json
import os
import uuid
from typing import Dict, Any, Optional, Tuple
import requests

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "video_quality": "1080p",
    "audio_quality": "192k",
    "audio_lang": "ja-JP",
    "subs_lang": "en-US",
    "force_download": False,
}


def save_config(config_dict: Dict[str, Any], config_path: str = CONFIG_FILE) -> None:
    """save settings"""
    existing: Dict[str, Any] = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    existing.update(config_dict)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save config to {config_path}: {e}")


def load_config(config_path: str = CONFIG_FILE) -> Dict[str, Any]:
    """load config if it exists, or automatically create it with defaults if missing"""
    if not os.path.exists(config_path):
        try:
            save_config(DEFAULT_CONFIG, config_path)
            return dict(DEFAULT_CONFIG)
        except Exception:
            return dict(DEFAULT_CONFIG)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dict(DEFAULT_CONFIG)


def get_device_id(config_path: str = CONFIG_FILE) -> str:
    """Retrieve the persistent device ID from config or generate and save a new one."""
    cfg = load_config(config_path)
    dev_id = cfg.get("device_id")
    if dev_id and isinstance(dev_id, str) and dev_id.strip():
        return dev_id.strip()
    new_id = str(uuid.uuid4())
    save_config({"device_id": new_id}, config_path)
    return new_id


def _get_device_id_val() -> str:
    try:
        return get_device_id()
    except Exception:
        return str(uuid.uuid4())


_DEVICE_ID = _get_device_id_val()


def get_access_token(etp_rt: str) -> str:
    """swap our session cookie for a bearer token"""
    dev_id = get_device_id()
    url = "https://www.crunchyroll.com/auth/v1/token"
    headers = {
        "Authorization": "Basic bm9haWhkZXZtXzZpeWcwYThsMHE6",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }
    cookies = {
        "device_id": dev_id,
        "etp_rt": etp_rt,
    }
    data = {
        "grant_type": "etp_rt_cookie",
        "device_id": dev_id,
        "device_type": "Chrome on Windows",
    }

    response = requests.post(url, headers=headers, cookies=cookies, data=data, timeout=20)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to get access token (status {response.status_code}): {response.text}"
        )

    json_resp = response.json()
    return json_resp.get("access_token", "")
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
