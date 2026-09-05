import os
import shutil
import subprocess
import sys
import zipfile

def build():
    print("=== Building crunchyroller Standalone Executable ===")
    
    # 1. ensure pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. collect data files to bundle
    root = os.path.dirname(os.path.abspath(__file__))
    sep = ";" if sys.platform == "win32" else ":"

    datas = [
        (os.path.join(root, "web"), "web"),
    ]

    for extra in ["ffmpeg.exe"]:
        p = os.path.join(root, extra)
        if os.path.exists(p):
            datas.append((p, "."))

    data_args = []
    for src, dst in datas:
        data_args.extend(["--add-data", f"{src}{sep}{dst}"])

    # 3. pyinstaller arguments
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",  # no black cmd prompt box
        "--name=crunchyroller",
        "--collect-all=crunchyroll",
        "--hidden-import=Crypto",
        "--hidden-import=pywidevine",
        "--hidden-import=pymp4",
        "--hidden-import=curl_cffi",
        "--hidden-import=webview",
        *data_args,
        os.path.join(root, "main.py"),
    ]

    print("Running command:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=root)
    
    dist_dir = os.path.join(root, "dist", "crunchyroller")
    readme_path = os.path.join(dist_dir, "README.txt")

    # Copy ffmpeg.exe to dist_dir root next to crunchyroller.exe
    ffmpeg_src = os.path.join(root, "ffmpeg.exe")
    ffmpeg_dst = os.path.join(dist_dir, "ffmpeg.exe")
    if os.path.exists(ffmpeg_src) and not os.path.exists(ffmpeg_dst):
        shutil.copy2(ffmpeg_src, ffmpeg_dst)

    readme_content = """========================================================================
                      CRUNCHYROLLER v2.0.0
========================================================================

HOW TO RUN:
Double-click 'crunchyroller.exe' to launch the application.

------------------------------------------------------------------------
REQUIREMENTS:
------------------------------------------------------------------------

1. WIDEVINE DRM KEYS (REQUIRED FOR DECRYPTION):
   Crunchyroll encrypts video/audio streams using Widevine DRM.
   You MUST provide your own Widevine key files to download/decrypt videos.

   Place ONE of the following directly inside this folder (next to crunchyroller.exe):

   - Option A (Easiest): A '.wvd' file (e.g. device.wvd)
   - Option B: 'client_id.bin' AND 'private_key.pem' files

   * Note: Widevine keys are NOT bundled with this release for legal reasons.
     Search online for "ready to use CDMs" or extract keys via Android Studio.

2. FFMPEG (INCLUDED):
   'ffmpeg.exe' is already pre-packaged in this folder.
   You DO NOT need to install FFmpeg separately.

3. MICROSOFT EDGE WEBVIEW2:
   Required to display the native app window.
   If WebView2 is missing on your PC, the app will show a prompt to download
   and install it automatically from Microsoft.

------------------------------------------------------------------------
WHAT'S NEW IN v2.0.0:
------------------------------------------------------------------------
- Bypassed CDN Speed Limit: Uses the mobile download endpoint to bypass
  the ~1 MB/s rate limit on standard web playback streams.
- Persistent Device ID: Eliminated 420/429 rate limit issues by maintaining
  a persistent client identity and proper stream session cleanup.
- Multi-Track Audio & Subtitles: Download all available audio dubs and soft
  subtitles multiplexed into MKV with explicit default track flags.
- Force Download: Added Web GUI toggle and --force-download CLI option.
- Android TV Login: Native login support with automatic session renewal.
- Direct SegmentBase Streaming: Chunked downloads and live progress for
  unsegmented titles (e.g. Blue Lock).
- Multi-KID Decryption: Fixed decryption key assignment for multi-track audio.
- CDN Mirror Selection: Automatic mirror detection and -x / --server option.
- Network Tuning: Configured 1 MB socket receive buffers and TCP_NODELAY.

------------------------------------------------------------------------
WHAT'S NEW IN v1.2.1:
------------------------------------------------------------------------
- Fixed: PSSH not found in MPD manifest for certain series (e.g. Blue Lock)
- Chunked streaming download for unsegmented / SegmentBase streams

------------------------------------------------------------------------
WHAT'S NEW IN v1.2.0:
------------------------------------------------------------------------
- High-Performance Download Pipeline with AIMD Adaptive Concurrency
- In-Order Stream Assembler to prevent RAM spikes and OOM crashes
- Private Discord Remote Control Bot (/download, /status, /queue, /cancel)
- Real-Time Dynamic Progress Dashboard & Episode Picker
- Zero-scrollbar minimalist UI styling with animated vector logo

------------------------------------------------------------------------
NEED HELP?
------------------------------------------------------------------------
- GitHub: https://github.com/Vure-sh/crunchyroller
- Discord: .vure
========================================================================
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)

    exe_path = os.path.join(dist_dir, "crunchyroller.exe")
    print(f"\nSuccess! Portable app built at:\n{exe_path}\nREADME generated at:\n{readme_path}")

    # 4. create release zip archive
    zip_name = "crunchyroller-v2.0.0-win64.zip"
    zip_path = os.path.join(root, zip_name)
    print(f"\nCompressing release into {zip_name}...")
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for folder_name, subfolders, filenames in os.walk(dist_dir):
            for filename in filenames:
                file_path = os.path.join(folder_name, filename)
                arcname = os.path.relpath(file_path, os.path.dirname(dist_dir))
                zipf.write(file_path, arcname)

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Created release zip: {zip_path} ({zip_size_mb:.1f} MB)")

if __name__ == "__main__":
    build()

