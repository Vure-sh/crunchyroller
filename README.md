<div align="center">

# Crunchyroller — Crunchyroll Downloader

**A fast Crunchyroll anime downloader with a modern GUI and CLI to download Crunchyroll videos with multi-audio, soft subtitles, unthrottled speeds, and Widevine DRM decryption into MKV.**

[![Release](https://img.shields.io/github/v/release/Vure-sh/crunchyroller?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases/latest)
[![Stars](https://img.shields.io/github/stars/Vure-sh/crunchyroller?color=ffd700&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/stargazers)
[![Downloads & Clones](https://img.shields.io/badge/Downloads%20%26%20Clones-250%2B-black?style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases)

---

<img width="1816" alt="Crunchyroller Interface" src="https://github.com/user-attachments/assets/e064a2ad-f2c8-40d8-93a6-f32b9a72cb24" />

</div>

---

## Features

- **Uncapped download speeds:** Downloads aren't throttled at all — it maxes out whatever your internet connection can handle (can reach 60–70+ MB/s on fast connections).
- **Clean Desktop GUI & CLI:** Run it as a sleek desktop app, in your web browser, or straight from the command line.
- **Multiple audio dubs & soft subtitles:** Pick Japanese, English, or download all available dubs and subs in one go, muxed cleanly into a single MKV.
- **Anti-ban protections (experimental):** Helps avoid stream lockouts and `KAT-3002` errors with automatic session cleanup and pacing. Still experimental, so please don't spam requests.
- **Automated Widevine DRM decryption:** Handles CENC decryption automatically once you provide your CDM keys (`.wvd` or `client_id.bin` + `private_key.pem`).
- **Easy login:** Sign in directly with your email/password, your web browser session, or by pasting an `etp_rt` cookie.
- **Batch anime downloader:** Queue up an entire season, whole series, or a text file of URLs.

---

## Getting Started

### Windows (Pre-built)
1. Download the latest release from [**Releases**](https://github.com/Vure-sh/crunchyroller/releases/latest).
2. Extract the zip.
3. Put your Widevine CDM files in the folder (see below).
4. Run `crunchyroller.exe`.

### Running from Source
Make sure you have **Python 3.10+** and [**FFmpeg**](https://ffmpeg.org/) installed.

```bash
git clone https://github.com/Vure-sh/crunchyroller.git
cd crunchyroller
pip install -r requirements.txt

# Run the app
python main.py --gui       # desktop window
python main.py --browser   # or in your browser
```

---

## Widevine Keys

Crunchyroll content is protected by Widevine DRM, so you need CDM keys to decrypt the video files.

Drop either of these into the app folder (next to `crunchyroller.exe` or in the project root):
- A `*.wvd` file, **or**
- Both `client_id.bin` and `private_key.pem`

*(Keys can't be bundled here for obvious reasons. You can dump them from an Android device or find them online).*

---

## CLI Usage

If you prefer using the terminal as a CLI downloader:

```bash
# Log in with your account (recommended for faster downloads and 192k audio)
python main.py --email "user@example.com" --password "your_password" --url "https://www.crunchyroll.com/watch/..."

# Download a single episode in 1080p
python main.py --url "https://www.crunchyroll.com/watch/..." --video-quality 1080p

# Download with specific audio dubs and subtitles
python main.py --url "https://www.crunchyroll.com/watch/..." --audio-lang "ja-JP,en-US" --subs-lang "en-US,es-419"

# Download all available dubs and subs
python main.py --url "https://www.crunchyroll.com/watch/..." --audio-lang all --subs-lang all

# Download a season or full series
python main.py --url "https://www.crunchyroll.com/series/..." --season 1
python main.py --url "https://www.crunchyroll.com/series/..."

# Batch download from a file (one URL per line)
python main.py --file urls.txt
```

Run `python main.py --help` to see all available flags.

---

## Star the Repo

If Crunchyroller helped you out, consider dropping a star on GitHub! It really helps more people discover the project.

---

## Disclaimer

This project is intended for personal backups and educational use only. Please support the official creators and license holders by keeping an active Crunchyroll subscription.

---

<sub>Keywords: crunchyroll downloader, crunchyroll anime downloader, download crunchyroll anime, crunchyroll video downloader, crunchyroll widevine, crunchyroll gui, crunchyroll cli, crunchyroll batch download, crunchyroll mkv, kat-3002 fix</sub>
