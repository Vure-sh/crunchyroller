import os
import shutil
import subprocess
import sys
import zipfile

def build():
    print("=== Building crunchyroller v3.5.1 Standalone Executable ===")
    
    # 1. ensure pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    root = os.path.dirname(os.path.abspath(__file__))

    # Clean previous build directories to ensure pristine output
    dist_dir = os.path.join(root, "dist", "crunchyroller")
    build_dir = os.path.join(root, "build")
    if os.path.exists(dist_dir):
        print(f"Cleaning previous dist directory: {dist_dir}")
        shutil.rmtree(dist_dir, ignore_errors=True)
    if os.path.exists(build_dir):
        print(f"Cleaning previous build directory: {build_dir}")
        shutil.rmtree(build_dir, ignore_errors=True)

    spec_path = os.path.join(root, "crunchyroller.spec")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        spec_path,
    ]

    print("Running command:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=root)
    
    readme_path = os.path.join(dist_dir, "README.txt")

    # Copy ffmpeg.exe to dist_dir root next to crunchyroller.exe
    ffmpeg_src = os.path.join(root, "ffmpeg.exe")
    ffmpeg_dst = os.path.join(dist_dir, "ffmpeg.exe")
    if os.path.exists(ffmpeg_src) and not os.path.exists(ffmpeg_dst):
        print(f"Copying ffmpeg.exe to {ffmpeg_dst}...")
        shutil.copy2(ffmpeg_src, ffmpeg_dst)

    # Copy bin/ directory structure for N_m3u8DL-RE support
    bin_src = os.path.join(root, "bin")
    bin_dst = os.path.join(dist_dir, "bin")
    if os.path.exists(bin_src):
        print(f"Copying bin directory to {bin_dst}...")
        shutil.copytree(bin_src, bin_dst, dirs_exist_ok=True)

    readme_content = """========================================================================
                      CRUNCHYROLLER v3.5.1
========================================================================

HOW TO RUN:
Double-click 'crunchyroller.exe' to launch the desktop application.

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
WHAT'S NEW IN v3.5.1:
------------------------------------------------------------------------
- Native Desktop Window Launch Fix (Fixes #13):
  Automatically strips Windows Mark-of-the-Web (Zone.Identifier) NTFS flags
  from bundled binaries on launch so WebView2 and .NET assemblies load
  cleanly after extracting release archives via Windows Explorer.
- One-Click "Open Folder" Shortcuts:
  Added an "open" button right next to the download directory browse button,
  an "open folder" button in the progress panel when downloads finish, and
  a reveal button in download history to highlight completed files in Explorer.

------------------------------------------------------------------------
WHAT'S NEW IN v3.5.0:
------------------------------------------------------------------------
- GitHub Release Update Checker:
  The app automatically checks for new releases on startup and displays an
  update notification button in the header when a newer version drops, plus a
  manual check button in Settings.
- Desktop Context Menu & Native Copy-Paste:
  Added a custom right-click context menu (Cut, Copy, Paste, Select All) with
  native Windows clipboard integration and enabled text selection.
- One-Click Log Tools:
  Added an "Open Logs Folder" button in Settings to jump straight to the log
  directory in Windows Explorer, plus a one-click "Copy Logs" button for bug reports.
- Streamlined UI:
  Cleaned up the star button hover effect and removed the star prompt banner.

------------------------------------------------------------------------
WHAT'S NEW IN v3.4.0:
------------------------------------------------------------------------
- WebView2 Native Window Fix (Fixes #7):
  Bundled pythonnet, clr_loader, and WebView2Loader interop binaries directly
  into the Windows build so native desktop windows launch reliably.
- Official Season & Arc Folder Naming:
  Directories are now automatically named after Crunchyroll's official arc
  titles with clean fallback and legacy season directory migration.
- Embedded Chapter Markers & CC Labeling (Closes #10):
  Automatically extracts intro, recap, and outro chapters from stream metadata
  and embeds them into MKV containers, preserving distinct English CC labels.
- Silent Subprocess Execution (Closes #11):
  Suppressed annoying black command prompt popups during ffmpeg and ffprobe
  muxing operations on Windows.
- Session Pool & Timeout Hardening:
  Raised connection and read timeouts to prevent socket drops, and enabled
  automatic orphan stream session cleanup for web accounts.

------------------------------------------------------------------------
WHAT'S NEW IN v3.3.1:
------------------------------------------------------------------------
- Bitrate Preference Selection:
  Choose between highest quality (default) and data-saver mode (lowest bitrate)
  directly in GUI settings or via --bitrate CLI flag.
- Improved Native Window Logic:
  Cleaned up WebView2 runtime detection and fallback behavior.
- Subtitle & MPD Enhancements:
  Improved DASH MPD parsing and track resolution.

------------------------------------------------------------------------
WHAT'S NEW IN v3.3.0:
------------------------------------------------------------------------
- Cross-Run Resume for Interrupted Downloads:
  If a download is interrupted, closed, or encounters a network drop,
  Crunchyroller tracks downloaded segments in a partials directory and
  resumes right from where it left off instead of starting from 0%.
- Persistent Queue & History:
  Your active queue, series tasks, and download history are now stored
  persistently across app restarts (in queue_state.json).
- Minimal Monochrome UI & Tabbed Settings:
  Completely redesigned interface with sleek monochrome aesthetic, tabbed
  settings panel, partials cache cleaner, and clear task/history controls.
- Muxing & MediaInfo Tagging Fixes:
  Eliminated the 98% muxing hang, improved ffprobe discovery, and added
  accurate BPS / bitrate metadata tags for MediaInfo and media servers.
- Native Windows App Icon:
  Pre-bundled official high-resolution application icon for crunchyroller.exe.

------------------------------------------------------------------------
WHAT'S NEW IN v3.1.0:
------------------------------------------------------------------------
- Custom Download Directory:
  You can now choose exactly where your downloads go right from the GUI
  using the new folder browse button, or pass -o / --output-dir in CLI.
- Clean Default Subfolder:
  Downloads now default into an 'anime/' folder instead of dumping files
  into your root app directory.
- Media Server Structure:
  Keeps the standard Plex and Jellyfin Season XX hierarchy inside your
  chosen download directory with seamless legacy file migration.

------------------------------------------------------------------------
WHAT'S NEW IN v3.0.0:
------------------------------------------------------------------------
- Thread-Safe FIFO Download Queue:
  Queue multiple episodes, seasons, or series simultaneously. Monitor all
  tasks in real time with the new sliding queue drawer and live controls.
- Anime Task Grouping & Progress Meter:
  Episodes are organized in clean collapsible accordion cards grouped by
  anime series. Features a circular SVG progress meter indicating overall
  series download status.
- Pause, Resume, and Granular Cancellation:
  Full control over downloads. Pause and resume running downloads on the
  fly, or cancel specific individual episodes without affecting the rest
  of the queue.
- Plex and Jellyfin Media Server Compliance:
  Downloads are automatically organized into standard media server layout:
  "<Anime Title>/Season <XX>/<Anime Title> - S<XX>E<YY> - <Episode Title>.mkv"
- Permanent Stream Limit Protection:
  Proactive auto-purging of orphaned stream playback sessions and dual-
  endpoint cleanup to prevent 420/429 rate limits and KAT-3002 errors.
- English CC & Multi-Subtitle Preservation:
  Preserves distinct English CC subtitle tracks without locale collision
  against standard English soft subs (fixes #6).
- Hardened CENC MP4 Parser:
  Added box guards and thread-safe decryption to prevent worker race
  conditions and fragmented MP4 stream corruption.
- Network & Resource Cleanup:
  Interruptible backoff timers, automatic cleanup of temporary download
  directories, and client socket cleanup.

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
    zip_name = "crunchyroller-v3.5.1-win64.zip"
    zip_path = os.path.join(root, zip_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    print(f"\nCompressing release into {zip_name}...")
    
    forbidden_files = {"client_id.bin", "private_key.pem", "config.json", ".env", "queue_state.json", "crunchyroller.log"}
    forbidden_exts = {".wvd", ".mkv", ".mp4", ".m4a", ".tmp"}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for folder_name, subfolders, filenames in os.walk(dist_dir):
            if ".cr_partials" in folder_name:
                raise RuntimeError(f"SECURITY ALERT: Found forbidden folder '{folder_name}' in distribution directory!")
            for filename in filenames:
                lower_name = filename.lower()
                _, ext = os.path.splitext(lower_name)
                if lower_name in forbidden_files or ext in forbidden_exts:
                    raise RuntimeError(f"SECURITY ALERT: Found forbidden file '{filename}' in distribution directory! Packaging aborted.")

                file_path = os.path.join(folder_name, filename)
                arcname = os.path.relpath(file_path, os.path.dirname(dist_dir))
                zipf.write(file_path, arcname)

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"Created release zip: {zip_path} ({zip_size_mb:.1f} MB)")

if __name__ == "__main__":
    build()
