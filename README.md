<div align="center">

# 🎬 Crunchyroller

**Production-ready Desktop App, CLI & Discord Bot to download Crunchyroll anime in full quality.**  
Multi-threaded DASH downloads, multiple audio & subtitle tracks, Widevine DRM decryption, and auto-muxing to MKV.

[![Release](https://img.shields.io/github/v/release/Vure-sh/crunchyroller?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases/latest)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-black?style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10%2B-black?style=for-the-badge&logo=python)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-black?style=for-the-badge)](LICENSE)

[**📥 Download Latest Release**](https://github.com/Vure-sh/crunchyroller/releases/latest) • [**✨ Features**](#-features) • [**🔑 Widevine Setup**](#-widevine-keys-required) • [**💻 CLI Reference**](#-cli-reference) • [**🤖 Discord Bot**](#-discord-bot-remote-control) • [**⚙️ Developer Setup**](#-developer-setup)

---

<img width="1816" alt="Crunchyroller Interface" src="https://github.com/user-attachments/assets/e064a2ad-f2c8-40d8-93a6-f32b9a72cb24" />

</div>

---

## ✨ Features

- 🖥️ **Modern Glassmorphism Desktop UI**: Minimalist native app window powered by PyWebView, with fallback to your default browser.
- ⚡ **Multi-Threaded DASH Downloader**: High-speed segmented downloading for individual episodes, full seasons, or complete series.
- 🔊 **Multi-Audio & Multi-Subtitles**: Select multiple dub tracks (Japanese, English, Spanish, French, German, etc.) and soft subtitles multiplexed together.
- 🔑 **Widevine DRM Decryption**: Automated CENC stream decryption using your Widevine device keys (`.wvd` or `client_id.bin` + `private_key.pem`).
- 🌐 **In-App Session Capture**: Automatically captures and stores your `etp_rt` session token via web login or browser cookie detection.
- 🎬 **FFmpeg Auto-Muxing**: Merges video streams, all audio tracks, soft subtitles, embedded fonts, and metadata directly into a clean `.mkv` file.
- 🤖 **Discord Bot Remote Control**: Trigger and queue downloads directly from your phone via interactive Discord slash commands with live progress embeds.
- 💻 **Versatile CLI Mode**: Full command-line interface with batch downloading from text files and granular stream selection.
- 📱 **Android Auth Companion**: Integrated companion module for mobile authentication flows.

---

## 🚀 Quick Start (Portable Executable)

For Windows users who don't want to install Python:

1. Download the latest **`crunchyroller-*-win64.zip`** from [**Releases**](https://github.com/Vure-sh/crunchyroller/releases/latest).
2. Extract the ZIP archive.
3. Place your **Widevine keys** (see [Widevine Keys](#-widevine-keys-required)) inside the extracted `crunchyroller/` folder next to `crunchyroller.exe`.
4. Double-click `crunchyroller.exe` to launch the GUI!

---

## 🔑 Widevine Keys (Required)

Crunchyroll protects its streams using Widevine DRM. To decrypt and download videos, provide your Widevine CDM device keys.

Place **ONE** of the following setups inside the project root (or next to `crunchyroller.exe`):

* **Option A (Recommended):** A `*.wvd` device file
* **Option B:** Both `client_id.bin` and `private_key.pem` files

> [!NOTE]
> Widevine device keys cannot be distributed with this project for legal reasons. Search for *"ready to use CDMs"* or use Android Studio / dumping tools to generate your own.

---

## ⚙️ Developer Setup (Run from Source)

### 1. Prerequisites
* **Python 3.10+**
* [**FFmpeg**](https://ffmpeg.org/) installed and available in your system `PATH` (or placed in the project root).

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Vure-sh/crunchyroller.git
cd crunchyroller

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Launching GUI
```bash
# Launch native desktop GUI (PyWebView)
python main.py --gui

# Launch web GUI in your default browser
python main.py --browser
```

---

## 🤖 Discord Bot (Remote Control)

Control and monitor downloads remotely from Discord on your phone or PC:

1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications) and obtain your bot token.
2. Create a `.env` file in the project root:
   ```env
   DISCORD_BOT_TOKEN=your_bot_token_here
   ```
3. Start the bot:
   ```bash
   python discord_bot.py
   ```

### Bot Commands
* `/download [url]` — Open an interactive picker with season selection, multiselect dropdowns, and custom range modals.
* `/status` — View real-time auto-updating embed dashboard (download speed, segment progress, and active queue).
* `/cancel` — Cancel current download and clear the queue.

---

## 💻 CLI Reference

Crunchyroller can be fully driven from the terminal:

> [!TIP]
> **Fast Downloads via Android TV Login:**  
> For maximum download speeds (bypassing the ~1 MB/s CDN throttle) and true 192k audio quality, log in using your Crunchyroll credentials (`--email` & `--password` in the CLI or Android TV login in the GUI). This unlocks the high-speed mobile `/download` CDN stream distribution.

### Common Commands

```bash
# Log in with credentials for fast downloads & 192k audio (recommended)
python main.py --email "user@example.com" --password "your_password" --url "https://www.crunchyroll.com/watch/..."

# Download a single episode in 1080p
python main.py --url "https://www.crunchyroll.com/watch/..." --video-quality 1080p

# Download with multiple audio dubs and subtitle languages
python main.py --url "https://www.crunchyroll.com/watch/..." --audio-lang "ja-JP,en-US" --subs-lang "en-US,es-419"

# Download every available audio dub and subtitle track
python main.py --url "https://www.crunchyroll.com/watch/..." --audio-lang all --subs-lang all

# Select a specific CDN server mirror (if available in manifest)
python main.py --url "https://www.crunchyroll.com/watch/..." -x 2

# Force redownload and replace an existing MKV
python main.py --url "https://www.crunchyroll.com/watch/..." --force-download

# Download an entire season
python main.py --url "https://www.crunchyroll.com/series/..." --season 1

# Download entire series (all seasons)
python main.py --url "https://www.crunchyroll.com/series/..."

# Batch download multiple URLs from a text file (one URL per line)
python main.py --file urls.txt

# Specify your etp_rt token manually
python main.py --etp-rt "YOUR_ETP_RT_COOKIE" --url "https://www.crunchyroll.com/watch/..."
```

> [!NOTE]
> When multiple audio or subtitle tracks are downloaded, the first selected track of each type is marked as the default in the generated MKV file. Other tracks remain available for selection. With `all`, the default follows the order returned by Crunchyroll's metadata.

### CLI Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--gui` | Flag | `False` | Launch native desktop GUI app window |
| `--browser` | Flag | `False` | Open GUI in default web browser instead of native window |
| `--email` | String | `""` | User email for Android TV authentication (recommended) |
| `--password` | String | `""` | User password for Android TV authentication |
| `--url` | String | `""` | URL of the episode, season, or series to download |
| `--file` | String | `""` | Path to a text file containing URLs (one per line) |
| `--audio-lang` | String | `ja-JP` | Audio language(s), comma-separated (e.g. `ja-JP,en-US`), or `all` for every available dub. First is default. |
| `--subs-lang` | String | `en-US` | Subtitle language(s), comma-separated (e.g. `en-US,es-419`), or `all` for every available subtitle. First is default. |
| `--video-quality` | String | `1080p` | Target video resolution (`1080p`, `720p`, `480p`, `360p`) |
| `--audio-quality` | String | `192k` | Target audio bitrate (`192k`, `96k`) |
| `-x`, `--server` | Integer | `1` | CDN server/mirror index from manifest (1 to N) |
| `--workers` | Integer | `8` | Worker concurrency for downloading segments |
| `--season` | Integer | `0` | Season number filter (used for series links; `0` downloads all) |
| `--etp-rt` | String | `""` | Crunchyroll `etp_rt` authentication cookie value |
| `--debug-manifest`| Flag | `False` | Log raw episode playback JSON and DASH manifest XML |
| `--force-download` | Flag | `False` | Redownload completed episodes and atomically replace existing MKV files |

---

## 📁 Repository Structure

```
crunchyroller/
├── android/                 # Android Companion App
│   └── app/src/main/        # Mobile auth & WebView session manager
├── crunchyroll/             # Core Downloader & API Logic
│   ├── api.py               # Crunchyroll API parser (Series, Seasons, Episodes)
│   ├── auth.py              # Auth handler & cookie capturer
│   ├── downloader.py        # Multi-threaded DASH stream downloader
│   ├── drm.py               # PyWidevine license exchange & CENC decryption
│   ├── http_client.py       # Resilient HTTP client with Cloudflare bypass
│   ├── merger.py            # FFmpeg / mkvmerge multiplexer
│   ├── mpd.py               # DASH manifest XML parser
│   ├── token.py             # Anonymous token generator
│   ├── types.py             # Data models & structures
│   └── utils.py             # Filename sanitization & path utilities
├── web/                     # Minimalist B&W Glassmorphism Web UI
│   ├── index.html
│   ├── css/
│   └── js/
├── discord_bot.py           # Remote control Discord bot with live embed dashboard
├── main.py                  # CLI & App entry point
├── web_gui.py               # PyWebView window & HTTP REST API handler
├── requirements.txt         # Python package dependencies
└── README.md
```

---

## 💬 Community & Support

* 🐛 Found a bug or have a suggestion? Open an [**Issue**](https://github.com/Vure-sh/crunchyroller/issues).
* 💬 Discord: **`.vure`**

---

## ⚠️ Disclaimer

This project is intended strictly for personal backups and educational purposes. Downloading copyrighted content may violate Crunchyroll's Terms of Service. The maintainers take no responsibility for misuse of this software.
