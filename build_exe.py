import os
import shutil
import subprocess
import sys
import zipfile

from crunchyroll import __version__

def build():
    print(f"=== Building crunchyroller v{__version__} Standalone Executable ===")
    
    # 1. ensure pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    root = os.path.dirname(os.path.abspath(__file__))

    # Ensure no previous crunchyroller process is locking dist files
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/IM", "crunchyroller.exe"], capture_output=True)

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

    readme_content = f"""========================================================================
                      CRUNCHYROLLER v{__version__}
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

2. FFMPEG:
   - Full Release: 'ffmpeg.exe' is already pre-packaged in this folder.
   - No-FFmpeg Release: Requires FFmpeg installed and accessible in your system PATH.

3. MICROSOFT EDGE WEBVIEW2:
   Required to display the native app window.
   If WebView2 is missing on your PC, the app will show a prompt to download
   and install it automatically from Microsoft.

------------------------------------------------------------------------
WHAT'S NEW IN v3.9.1:
------------------------------------------------------------------------
- Late-Dub Retry in Auto-Downloader (Fixes #24):
  Episodes airing initially without dubs (when audio fallback is off) now stay
  pending rather than getting swallowed into known_episodes, automatically downloading
  when dub versions drop. Automatically heals previously skipped series.
- Per-Series Auto-DL Overrides:
  Each monitored anime card features a dedicated settings gear to customize audio
  language, subtitles, video quality, download folder, and audio fallback specifically
  for that show. Cards show a CUSTOM badge when overrides are active.
- Python 3.10 & 3.11 Compatibility:
  Extracted nested f-string expressions in skip messages to eliminate SyntaxError
  on Python <3.12.
- UI Contrast AA Compliance (Fixes #23):
  Raised text contrast from low-contrast #555 to #8f8f8f (WCAG AA) and adjusted
  secondary font sizes across the dashboard for clearer readability.
- Auto-DL Streamlined Toolbar & Accessibility:
  Replaced double header rows with a streamlined toolbar featuring a keyboard-
  accessible pause/resume status button, quick-check button, compact filter dropdown,
  and direct add anime workflow.
- Downloader Audio Locale Matching:
  Added base audio locale resolution for episodes with limited metadata to prevent
  spurious AudioUnavailableError exceptions.

------------------------------------------------------------------------
WHAT'S NEW IN v3.9.0:
------------------------------------------------------------------------
- Auto-Downloader & Watcher Tab:
  Added a dedicated 'auto-dl' tab to monitor ongoing series and automatically grab new episodes on a configurable interval (15m to 24h, plus a 30s test mode).
- Monitoring Modes (Future Only vs. All Missing):
  Set each series to Future Only (new episodes going forward) or All Missing (scans local Season XX/ folders and backfills missing episodes).
- In-Tab Search & Filters:
  Search Crunchyroll directly from the Auto-DL tab by title, URL, or ID, and filter tracked shows by status.
- Crunchyroll Watchlist Integration:
  Directly sync and explore your official Crunchyroll Watchlist/Crunchylists with multi-profile switching, PIN support, and one-click batch downloading or auto-dl tracking.
- Compact Expanding Navbar:
  Collapsed inactive nav tabs into icon-only buttons with tooltips, smoothly expanding the label on the active tab while keeping the auto-dl counter badge visible.
- Caching & Cleanup:
  Added 10-minute caching for the Recently Added feed and dropped Windows PowerShell toast dependencies to prevent background process leaks.

------------------------------------------------------------------------
WHAT'S NEW IN v3.8.1:
------------------------------------------------------------------------
- Audio Language Fallback Toggle (Addresses #22):
  - Added an 'audio language fallback' setting toggle in GUI Settings (enabled by default) and CLI flag (--audio-fallback / --no-audio-fallback).
  - Preserves logical fallback to original audio by default when a requested dub is missing.
  - When toggled off, episodes without the requested dub language are cleanly skipped in the queue instead of falling back to Japanese.
- Dual-Track Subtitles on Dub Downloads:
  - Resolved missing dialogue subtitles when downloading foreign audio (e.g. French, German dubs).
  - Automatically fetches the full dialogue subtitle catalog from the original/master stream
    while preserving the dub's native Signs & Songs (forced narrative) track.
  - Automatically sets default disposition for dialogue tracks so subtitles appear by default
    during speech across VLC, MPV, Plex, and Jellyfin, with cleanly labeled tracks
    (e.g. 'Français' and 'Français [Signs & Songs]').
- Subtitle Pipeline Overhaul (Fixes #20):
  - Prioritized official Web playback endpoint (web/chrome/play) for comprehensive
    multi-language .ass soft subtitle catalog retrieval, replacing empty/stub
    Android TV stream responses.
  - Multi-language alias resolution supporting 2-letter, 3-letter (ISO-639-2), and
    localized naming (fra, fre, french, deu, ger, german, spa, spanish, etc.).
  - Bearer authentication injection for protected CDN subtitle segment downloads.
  - Resolved relative DASH MPD AdaptationSet BaseURL tracks with manifest URLs.
  - Dub candidate search fallback now inspects primary Japanese streams and preserves
    dialogue translation tracks.
- Auth & Session Token Lifecycle Resilience:
  - Proactively refreshes expired Android TV access tokens before dispatching requests.
  - Intercepts HTTP 403 Forbidden playback errors alongside HTTP 401, automatically
    refreshing tokens and retrying requests without failing downloads.
  - Clean auth state synchronization when logging in with etp_rt or credentials,
    purging stale credentials to eliminate dead token shadowing.
  - Resilient catalog search with automatic fallback to guest token if user session
    has expired.

------------------------------------------------------------------------
WHAT'S NEW IN v3.8.0:
------------------------------------------------------------------------
- Recently Added Anime Catalog (#18):
  Explore newly added Crunchyroll anime in a dedicated tab with artwork, metadata,
  integrated search filtering, and multi-select queueing/fetching.
- Multi-Language Subtitle Preservation:
  Fixed mobile /download upgrade dropping non-English subtitles (fr-FR, de-DE, etc.).
- Candidate Dub Version Prioritization:
  Dub version discovery now prioritizes candidate streams matching requested subtitle locales.
- 64-bit Clipboard Safety (Fixes #19):
  Fixed silent access violation crash on Windows when right-click pasting URLs.
- Standalone Optimization:
  Removed unused binaries and packages from distribution bundles.

------------------------------------------------------------------------
WHAT'S NEW IN v3.7.1:
------------------------------------------------------------------------
- Windows Long Path Budgeting (Closes #17):
  Prevents [Errno 2] No such file or directory crashes on Windows when downloading
  series with lengthy titles. Output filenames and intermediate muxing paths
  are dynamically budgeted to remain safely within the 259-character MAX_PATH limit.
- Safe Temporary Chapter Metadata:
  FFmpeg chapter files are now created in the system temporary directory during muxing
  instead of appending to the destination path, avoiding path overflow.
- Connection Pool & Concurrency Expansion:
  Increased HTTP connection pool capacities across the session pool and worker queues
  to eliminate urllib3 connection pool exhaustion warnings during high concurrency.

------------------------------------------------------------------------
WHAT'S NEW IN v3.7.0:
------------------------------------------------------------------------
- Multi-Anime Batch Fetching & Grouped Queue:
  Enter multiple anime URLs at once (separated by commas or newlines), or select
  multiple series simultaneously from in-app search results. Each anime is
  automatically partitioned into its own distinct collapsible task card in the
  download queue.
- Queue Engine Hardening & Race Fixes:
  Resolved stuck failure spinners on all-failed batches (error) and mixed batches
  (partial_error). Fixed worker cancel/enqueue starvation race using generation tokens,
  protected queued partial downloads during cleanup, and fixed queue snapshots.
- Dual Release Packaging:
  Now offering both standard full Windows builds (with bundled FFmpeg) and lightweight
  no-ffmpeg archives for users with existing FFmpeg PATH installations.
- Live Repository Star Counter:
  Added a minimalist live star counter pill in the top navigation header with
  background caching and offline graceful fallback.
- Bundle Optimization:
  Eliminated duplicate bundled FFmpeg binaries in release distributions,
  significantly cutting unneeded package weight.

------------------------------------------------------------------------
WHAT'S NEW IN v3.6.0:
------------------------------------------------------------------------
- Audio & Subtitle Only Mode (Addresses #15):
  Download just audio tracks and subtitles without downloading video streams.
  Select 'audio only (no video)' from the Video Quality dropdown in GUI, or pass
  --no-video / --audio-only in CLI. Choose between .mka container (default), .mkv,
  or standalone .m4a with companion subtitle files.
- Anti-RateLimit Safe Mode & Pacing Controls (Addresses #14):
  Added configurable delay between episode downloads (default 60s, with ±5s jitter)
  and optional thread reduction to protect against KAT-3002 temporary blocks.
- Redesigned History View:
  Clean two-line episode card with series title, season/episode tags, quality,
  relative timestamp, file size, status pill, and one-click show-in-folder button.
- Progress & Phase Tracking:
  Added detailed percentage indicators on sub-bars and clear phase logging.

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

    # 4. create release zip archives (Full + No-FFmpeg)
    zip_name = f"crunchyroller-v{__version__}-win64.zip"
    zip_no_ffmpeg_name = f"crunchyroller-v{__version__}-win64-no-ffmpeg.zip"
    zip_path = os.path.join(root, zip_name)
    zip_no_ffmpeg_path = os.path.join(root, zip_no_ffmpeg_name)

    if os.path.exists(zip_path):
        os.remove(zip_path)
    if os.path.exists(zip_no_ffmpeg_path):
        os.remove(zip_no_ffmpeg_path)

    print(f"\nCompressing release into {zip_name} (with bundled FFmpeg)...")
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
    print(f"Created full release zip: {zip_path} ({zip_size_mb:.1f} MB)")

    print(f"\nCompressing lightweight release into {zip_no_ffmpeg_name} (no ffmpeg.exe)...")
    with zipfile.ZipFile(zip_no_ffmpeg_path, "w", zipfile.ZIP_DEFLATED) as zipf_slim:
        for folder_name, subfolders, filenames in os.walk(dist_dir):
            if ".cr_partials" in folder_name:
                continue
            for filename in filenames:
                lower_name = filename.lower()
                if lower_name == "ffmpeg.exe":
                    continue
                _, ext = os.path.splitext(lower_name)
                if lower_name in forbidden_files or ext in forbidden_exts:
                    continue

                file_path = os.path.join(folder_name, filename)
                arcname = os.path.relpath(file_path, os.path.dirname(dist_dir))
                zipf_slim.write(file_path, arcname)

    zip_slim_size_mb = os.path.getsize(zip_no_ffmpeg_path) / (1024 * 1024)
    print(f"Created no-ffmpeg release zip: {zip_no_ffmpeg_path} ({zip_slim_size_mb:.1f} MB)")

if __name__ == "__main__":
    build()
