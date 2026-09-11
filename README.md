<div align="center">

# Crunchyroller — Crunchyroll Downloader

**A fast Crunchyroll anime downloader with a modern GUI and CLI to download Crunchyroll videos with multi-audio, soft subtitles, unthrottled speeds, and Widevine DRM decryption into MKV.**

[![Release](https://img.shields.io/github/v/release/Vure-sh/crunchyroller?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases/latest)
[![Stars](https://img.shields.io/github/stars/Vure-sh/crunchyroller?color=ffd700&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/stargazers)
[![Downloads & Clones](https://img.shields.io/badge/Downloads%20%26%20Clones-250%2B-black?style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases)

---

<img width="848" height="746" alt="image" src="https://github.com/user-attachments/assets/bcd9dbb1-86dc-4560-beaf-c07dcc5c4a79" />


</div>

---

### Plex & Jellyfin Ready Out-of-the-Box

Downloads automatically sort into standard `Series/Season 01/Series - S01E01 - Title.mkv` folders so home media servers like Jellyfin and Plex instantly match official posters, episode guides, and multi-track audio without manual renaming:

<img width="1851" height="1034" alt="Jellyfin Library Showcase" src="https://github.com/user-attachments/assets/c2b945a5-ce6b-4f4c-9bb9-abfff0db4bee" />

---

## Features

- **Plex & Jellyfin Ready:** Automatically creates `Season XX` subfolders with standard scene naming (`Series - S01E01 - Title.mkv`), ensuring 100% instant metadata and poster matching in home media servers.
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

## Optional Download Engine: N_m3u8DL-RE

In addition to the built-in native Python downloader, Crunchyroller supports [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) as an alternative backend engine (thanks to [@AnCry1596](https://github.com/AnCry1596) for the implementation!).

### To use N_m3u8DL-RE (completely optional):
1. Download `N_m3u8DL-RE` and `mp4decrypt` (Bento4) for your platform and place them inside the `bin/` folder.
2. In `config.json`, enable the engine:
   ```json
   "use_n_m3u8dl_re": true
   ```

*(If set to `false`, Crunchyroller uses its built-in unthrottled pure-Python downloader).*

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

# List all available seasons and story arcs
python main.py --url "https://www.crunchyroll.com/series/..." --list-seasons

# Download a specific season or story arc
python main.py --url "https://www.crunchyroll.com/series/..." --season 1
python main.py --url "https://www.crunchyroll.com/series/..."

# Batch download from a file (one URL per line)
python main.py --file urls.txt
```

### Listing & Picking Seasons (No More Guessing)

Crunchyroll numbers seasons pretty weirdly behind the scenes — for example, *Demon Slayer's Mugen Train Arc* is actually listed as Season 4, and *Attack on Titan's OADs* are listed under Season 66.

Instead of guessing what number Crunchyroll gave to an arc or special, just use `--list-seasons` (or `-ls`):

```bash
python main.py --list-seasons https://www.crunchyroll.com/series/GY5P48XEY
```

You'll instantly get a clean breakdown with the real arc names and the exact `--season` flag to use:

```text
Seasons available for 'Demon Slayer: Kimetsu no Yaiba':
===================================================================
  --season 4   | Mugen Train Arc
  --season 5   | Entertainment District Arc
  --season 6   | Swordsmith Village Arc
  --season 7   | Hashira Training Arc
===================================================================
```

Then just download the arc you want:
```bash
python main.py https://www.crunchyroll.com/series/GY5P48XEY --season 4
```

*(You don't even need to type `--url`, you can pass the link directly! And yes, specials and movies listed under `--season 0` work too).*

Run `python main.py --help` to see all available flags.

---

## Star the Repo

If Crunchyroller helped you out, consider dropping a star on GitHub! It really helps more people discover the project.

---

## Disclaimer

This project is intended for personal backups and educational use only. Please support the official creators and license holders by keeping an active Crunchyroll subscription.

---

<sub>Keywords: crunchyroll downloader, crunchyroll anime downloader, download crunchyroll anime, crunchyroll video downloader, crunchyroll widevine, crunchyroll gui, crunchyroll cli, crunchyroll batch download, crunchyroll mkv, kat-3002 fix</sub>
