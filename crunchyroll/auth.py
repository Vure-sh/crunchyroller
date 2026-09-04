import json
import os
import threading
import time
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


def get_device_id(config_path: str = CONFIG_FILE) -> str:
    """Retrieve or generate and persist a stable device ID."""
    cfg = load_config(config_path)
    dev_id = cfg.get("device_id")
    if not dev_id:
        dev_id = str(uuid.uuid4())
        save_config({"device_id": dev_id}, config_path)
    return dev_id


_CACHED_TOKEN_LOCK = threading.Lock()
_CACHED_TOKEN_INFO: Dict[str, Any] = {
    "token": "",
    "etp_rt": "",
    "expires_at": 0.0,
}


def get_access_token(etp_rt: str) -> str:
    """swap our session cookie for a bearer token with caching"""
    now = time.monotonic()
    with _CACHED_TOKEN_LOCK:
        if (
            _CACHED_TOKEN_INFO["token"]
            and _CACHED_TOKEN_INFO["etp_rt"] == etp_rt
            and now < _CACHED_TOKEN_INFO["expires_at"]
        ):
            return _CACHED_TOKEN_INFO["token"]

    url = "https://www.crunchyroll.com/auth/v1/token"
    dev_id = get_device_id()
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
    token = json_resp.get("access_token", "")
    expires_in = float(json_resp.get("expires_in", 300))
    with _CACHED_TOKEN_LOCK:
        _CACHED_TOKEN_INFO["token"] = token
        _CACHED_TOKEN_INFO["etp_rt"] = etp_rt
        _CACHED_TOKEN_INFO["expires_at"] = time.monotonic() + max(expires_in - 30, 10)
    return token


def auto_detect_etp_rt() -> Optional[str]:
    """try to grab the etp_rt cookie from whatever browser is installed"""
    import glob
    import sqlite3
    import shutil
    import tempfile
    import base64
    import ctypes
    from ctypes import wintypes
    from Crypto.Cipher import AES

    # firefox
    ff_paths = [
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Mozilla", "Firefox", "Profiles", "*", "cookies.sqlite"),
        os.path.join(os.path.expanduser("~"), ".mozilla", "firefox", "*", "cookies.sqlite"),
    ]
    for pattern in ff_paths:
        for db in glob.glob(pattern):
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False).name
                shutil.copy2(db, tmp)
                conn = sqlite3.connect(tmp)
                c = conn.cursor()
                c.execute("SELECT value FROM moz_cookies WHERE host LIKE '%crunchyroll%' AND name='etp_rt'")
                row = c.fetchone()
                conn.close()
                os.remove(tmp)
                if row and row[0]:
                    return row[0]
            except Exception:
                pass

    # chromium browsers
    if os.name == "nt":
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        def unprotect_data(data):
            in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_byte)))
            out_blob = DATA_BLOB()
            if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
                res = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                ctypes.windll.kernel32.LocalFree(out_blob.pbData)
                return res
            return None

        def get_chrome_key(local_state_path):
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])[5:]
            return unprotect_data(encrypted_key)

        def decrypt_val(val, key):
            try:
                iv = val[3:15]
                payload = val[15:]
                cipher = AES.new(key, AES.MODE_GCM, iv)
                return cipher.decrypt(payload)[:-16].decode("utf-8")
            except Exception:
                return ""

        browsers = {
            "Brave": os.path.join(os.path.expanduser("~"), "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data"),
            "Chrome": os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data"),
            "Edge": os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Edge", "User Data"),
            "Opera": os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Opera Software", "Opera Stable"),
        }

        def copy_db_safely(src, dst):
            try:
                shutil.copy2(src, dst)
                return True
            except Exception:
                pass
            # try raw win32 read if file is locked
            try:
                GENERIC_READ = 0x80000000
                FILE_SHARE_READ = 0x00000001
                FILE_SHARE_WRITE = 0x00000002
                FILE_SHARE_DELETE = 0x00000004
                OPEN_EXISTING = 3
                handle = ctypes.windll.kernel32.CreateFileW(
                    ctypes.c_wchar_p(src), GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                    None, OPEN_EXISTING, 0, None
                )
                if handle != -1 and handle != 0xFFFFFFFF:
                    size = ctypes.windll.kernel32.GetFileSize(handle, None)
                    buf = ctypes.create_string_buffer(size)
                    bread = wintypes.DWORD()
                    ctypes.windll.kernel32.ReadFile(handle, buf, size, ctypes.byref(bread), None)
                    ctypes.windll.kernel32.CloseHandle(handle)
                    with open(dst, "wb") as f:
                        f.write(buf.raw[:bread.value])
                    return True
            except Exception:
                pass
            return False

        for name, bpath in browsers.items():
            lpath = os.path.join(bpath, "Local State")
            if not os.path.exists(lpath):
                continue

            cookie_candidates = glob.glob(os.path.join(bpath, "Default", "Network", "Cookies"))
            cookie_candidates.extend(glob.glob(os.path.join(bpath, "Profile *", "Network", "Cookies")))
            cookie_candidates.extend(glob.glob(os.path.join(bpath, "Cookies")))

            try:
                key = get_chrome_key(lpath)
                for cpath in cookie_candidates:
                    if os.path.exists(cpath):
                        tmp = tempfile.NamedTemporaryFile(delete=False).name
                        if copy_db_safely(cpath, tmp):
                            try:
                                conn = sqlite3.connect(tmp)
                                c = conn.cursor()
                                c.execute("SELECT encrypted_value FROM cookies WHERE host_key LIKE '%crunchyroll%' AND name='etp_rt'")
                                row = c.fetchone()
                                conn.close()
                                os.remove(tmp)
                                if row:
                                    dec = decrypt_val(row[0], key)
                                    if dec:
                                        return dec
                            except Exception:
                                if os.path.exists(tmp):
                                    try:
                                        os.remove(tmp)
                                    except Exception:
                                        pass
            except Exception:
                pass

    return None




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
    dev_id = device_id or str(uuid.uuid4())
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
    })
    return access_token, refresh_token


def refresh_android_tv_token(
    refresh_token: str, device_id: Optional[str] = None
) -> Tuple[str, str]:
    """Refreshes an expired Android TV access token.
    Returns (new_access_token, new_refresh_token).
    """
    dev_id = device_id or str(uuid.uuid4())
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
    })
    return new_access, new_refresh


def login_with_credentials(
    username: str, password: str, device_id_val: Optional[str] = None
) -> Tuple[str, str]:
    """Login with username & password using Android TV client to get native Android TV tokens."""
    return login_with_android_tv(username, password, device_id=device_id_val)


def open_webview_login() -> Optional[str]:
    """
    open a browser window to crunchyroll.com/login and grab the etp_rt cookie
    when the user logs in. works both standalone and inside a running pywebview app.
    """
    import threading
    import time

    try:
        import webview
    except ImportError:
        print("pywebview not installed, falling back to auto-detect")
        return auto_detect_etp_rt()

    captured = {"token": None, "done": False}

    def poll_cookies(window):
        """keep checking for the etp_rt cookie until we find it or the window closes"""
        # give the page a sec to load before we start hammering it
        time.sleep(2)
        while not captured["done"]:
            time.sleep(1)
            try:
                cookies = window.get_cookies()
                if cookies:
                    for c in cookies:
                        if hasattr(c, 'items'):
                            for k, m in c.items():
                                if k == 'etp_rt' and m.value:
                                    captured["token"] = m.value
                                    captured["done"] = True
                                    try:
                                        window.destroy()
                                    except Exception:
                                        pass
                                    return
            except Exception:
                # window probably closed
                captured["done"] = True
                return

    # check if webview event loop is already running (e.g. we're inside the desktop app)
    already_running = len(webview.windows) > 0

    try:
        w = webview.create_window(
            'Crunchyroll Login',
            'https://www.crunchyroll.com/login',
            width=960,
            height=720,
        )

        # start polling right away on a background thread
        poller = threading.Thread(target=poll_cookies, args=(w,), daemon=True)
        poller.start()

        if already_running:
            # event loop is already going, just wait for the login window to close
            while not captured["done"]:
                time.sleep(0.5)
        else:
            # no event loop yet, we need to start one (blocks until all windows close)
            webview.start()

        # give the poller a moment to finish up
        poller.join(timeout=2)

        if captured["token"]:
            return captured["token"]

        # didn't capture from cookies, try browser cookie jars as backup
        return auto_detect_etp_rt()

    except Exception as e:
        print(f"webview login failed ({e}), trying auto-detect...")
        return auto_detect_etp_rt()




