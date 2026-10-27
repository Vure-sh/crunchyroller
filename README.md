<div align="center">

# Crunchyroller

**A fast Crunchyroll downloader with a Web GUI and CLI. Download episodes, full seasons, or entire series with multi-track audio, soft subtitles, chapter markers, and automated Widevine DRM decryption into MKV.**

[![Release](https://img.shields.io/github/v/release/Vure-sh/crunchyroller?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Vure-sh/crunchyroller/total?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases)
[![Stars](https://img.shields.io/github/stars/Vure-sh/crunchyroller?color=ffd700&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/stargazers)

<br/>

<img width="800" alt="Crunchyroller Web GUI" src="https://github.com/user-attachments/assets/f632405c-2cbf-4fe8-8ff3-d8095cdf32d1" />

</div>

---

## Features

- **Web GUI & CLI:** Download via browser interface, desktop window (`--gui`), or directly from the terminal.
- **Multi-Track Audio & Soft Subtitles:** Download Japanese, English, or all available audio dubs and soft subtitles (including English CC) in a single MKV.
- **Official Chapter Markers:** Embeds Crunchyroll skip events (Intro, Outro, Credits, Preview) for one-click skipping in VLC, MPV, Plex, and Jellyfin.
- **Queue & Batch Downloads:** Queue episodes, full seasons, or series with live progress, pause, resume, and cancellation.
- **Plex & Jellyfin Ready:** Automatically organizes files into `Series/Season XX/Series - S01E01 - Title.mkv` for instant metadata matching.
- **Fast & Unthrottled:** Direct Widevine CENC decryption with maximum connection throughput.
- **Season Explorer:** Inspect and download tricky season numbers and story arcs with `--list-seasons`.

---

## Quick Start

### Windows (Pre-built)
1. Download the latest release from [Releases](https://github.com/Vure-sh/crunchyroller/releases/latest).
2. Extract the `.zip` archive.
3. Place your Widevine CDM files in the folder (see [Widevine Keys](#widevine-keys)).
4. Run `crunchyroller.exe`.

### From Source (Linux, macOS, Windows)
Requirements: **Python 3.10+** and [**FFmpeg**](https://ffmpeg.org/).

```bash
git clone https://github.com/Vure-sh/crunchyroller.git
cd crunchyroller
pip install -r requirements.txt

# Run the app
python main.py --gui       # desktop window
python main.py --browser   # in your default browser
```

---

## Widevine Keys

Crunchyroll streams are encrypted with Widevine DRM. Place either of the following in the app root directory:
- A `*.wvd` file, **or**
- `client_id.bin` and `private_key.pem`

*(Keys cannot be bundled with the project. You can dump them from an Android device).*

---

## CLI Examples

```bash
# Download a single episode in 1080p
python main.py "https://www.crunchyroll.com/watch/..." --video-quality 1080p

# Download with specific audio dubs and subtitles
python main.py "https://www.crunchyroll.com/watch/..." --audio-lang "ja-JP,en-US" --subs-lang "en-US,es-419"

# Download all available dubs and subs
python main.py "https://www.crunchyroll.com/watch/..." --audio-lang all --subs-lang all

# List story arcs and seasons
python main.py "https://www.crunchyroll.com/series/..." --list-seasons

# Download a specific season or arc
python main.py "https://www.crunchyroll.com/series/..." --season 1

# Batch download from a text file (one URL per line)
python main.py --file urls.txt
```

---

## Optional Download Engine: N_m3u8DL-RE

Crunchyroller uses its built-in Python downloader by default, but also supports [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) (thanks to [@AnCry1596](https://github.com/AnCry1596)):
1. Place `N_m3u8DL-RE` and `mp4decrypt` into the `bin/` folder.
2. In `config.json`, set `"use_n_m3u8dl_re": true`.

---

## Logs & Troubleshooting

Logs are stored locally with tokens and sensitive credentials automatically redacted:
- **Windows:** `%LOCALAPPDATA%\crunchyroller\logs\crunchyroller.log`
- **Linux:** `~/.config/crunchyroller/logs/crunchyroller.log`
- **macOS:** `~/Library/Logs/crunchyroller/crunchyroller.log`

---

## Disclaimer

This project is for personal backup and educational purposes only. Please support the official creators and license holders by maintaining an active Crunchyroll subscription.
