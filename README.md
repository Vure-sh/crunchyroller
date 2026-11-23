<div align="center" markdown="1">

# Crunchyroller

**Fast Crunchyroll downloader with a Web GUI and CLI. Multi-track audio, soft subs, chapter markers, auto Widevine decryption, into one MKV.**

[![Release](https://img.shields.io/github/v/release/Vure-sh/crunchyroller?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Vure-sh/crunchyroller/total?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases)
[![Stars](https://img.shields.io/github/stars/Vure-sh/crunchyroller?color=ffd700&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/stargazers)

<img width="800" alt="Crunchyroller dashboard" src="readme-assets/readme-dashboard.png" />

</div>

## Features

- **Web GUI, desktop window, or CLI**
- **Auto-Downloader** with per-series settings (audio, subs, quality, folder)
- **All dubs and soft subs in one MKV**, with skip chapters for Intro/Outro
- **Queue with pause/resume**, batch whole seasons or series
- **Plex/Jellyfin-ready naming** out of the box

## Auto-Downloader

Add an anime and new episodes download themselves. Each show gets its own mode (Future Only / All Missing) and its own settings via the gear on its card. Episodes airing before their dub stay pending until the dub drops.

<img width="800" alt="Auto-Downloader tab" src="readme-assets/readme-autodl.png" />
<img width="800" alt="Per-series settings" src="readme-assets/readme-series-settings.png" />

## Quick Start

**Windows:** grab the [latest release](https://github.com/Vure-sh/crunchyroller/releases/latest), drop your Widevine keys (`*.wvd`, or `client_id.bin` + `private_key.pem`) next to the exe, run it.

**From source** (Python 3.10+, FFmpeg):

```bash
git clone https://github.com/Vure-sh/crunchyroller.git && cd crunchyroller
pip install -r requirements.txt
python main.py --gui       # or --browser
```

## CLI

```bash
python main.py "<url>" --video-quality 1080p --audio-lang "ja-JP,en-US" --subs-lang "en-US"
python main.py "<series-url>" --season 1
python main.py --file urls.txt    # batch
```

**Optional:** [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) engine: put it + `mp4decrypt` in `bin/`, set `"use_n_m3u8dl_re": true`. Logs (auto-redacted) are in `%LOCALAPPDATA%\crunchyroller\logs` / `~/.config/crunchyroller/logs` / `~/Library/Logs/crunchyroller`.

## Community

- [crunchyroller-docker](https://github.com/CatChow0/crunchyroller-docker): run Crunchyroller in Docker, handy for servers and NAS. Thanks [@CatChow0](https://github.com/CatChow0)!

---

For personal backup and educational purposes only. Support the official creators with an active Crunchyroll subscription.
