<div align="center" markdown="1">

# Crunchyroller

**Fast Crunchyroll downloader.** Web GUI, desktop window, or CLI.
Multi-track audio, soft subs, skip chapters, auto decryption, one clean MKV.

[![Release](https://img.shields.io/github/v/release/Vure-sh/crunchyroller?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/Vure-sh/crunchyroller/total?color=black&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/releases)
[![Stars](https://img.shields.io/github/stars/Vure-sh/crunchyroller?color=ffd700&style=for-the-badge)](https://github.com/Vure-sh/crunchyroller/stargazers)

<img width="720" alt="Crunchyroller dashboard" src="readme-assets/readme-dashboard.png" />

</div>

## <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-sparkles-dark.svg"><img width="22" src="readme-assets/icon-sparkles-light.svg" alt=""></picture> Features

- <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-monitor-dark.svg"><img width="16" src="readme-assets/icon-monitor-light.svg" alt=""></picture> **Web GUI, desktop window, or CLI** - same app, your pick
- <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-download-dark.svg"><img width="16" src="readme-assets/icon-download-light.svg" alt=""></picture> **Auto-Downloader** with per-series settings (audio, subs, quality, folder)
- <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-headphones-dark.svg"><img width="16" src="readme-assets/icon-headphones-light.svg" alt=""></picture> **All dubs and soft subs in one MKV**, with skip chapters for Intro/Outro
- <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-repeat-dark.svg"><img width="16" src="readme-assets/icon-repeat-light.svg" alt=""></picture> **Queue with pause/resume**, batch whole seasons or series
- <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-tv-dark.svg"><img width="16" src="readme-assets/icon-tv-light.svg" alt=""></picture> **Plex/Jellyfin-ready naming** out of the box

## <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-download-dark.svg"><img width="22" src="readme-assets/icon-download-light.svg" alt=""></picture> Auto-Downloader

Add an anime and new episodes download themselves. Each show gets its own mode (Future Only / All Missing) and its own settings via the gear on its card. Episodes airing before their dub stay pending until the dub drops.

<div align="center" markdown="1">
<img width="49%" alt="Auto-Downloader tab" src="readme-assets/readme-autodl.png" /> <img width="49%" alt="Per-series settings" src="readme-assets/readme-series-settings.png" />
</div>

## <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-rocket-dark.svg"><img width="22" src="readme-assets/icon-rocket-light.svg" alt=""></picture> Quick Start

**Windows:** grab the [latest release](https://github.com/Vure-sh/crunchyroller/releases/latest), drop your Widevine keys (`*.wvd`, or `client_id.bin` + `private_key.pem`) next to the exe, run it.

**From source** (Python 3.10+, FFmpeg):

```bash
git clone https://github.com/Vure-sh/crunchyroller.git && cd crunchyroller
pip install -r requirements.txt
python main.py --gui       # or --browser
```

## <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-terminal-dark.svg"><img width="22" src="readme-assets/icon-terminal-light.svg" alt=""></picture> CLI

```bash
python main.py "<url>" --video-quality 1080p --audio-lang "ja-JP,en-US" --subs-lang "en-US"
python main.py "<series-url>" --season 1
python main.py --file urls.txt    # batch
```

**Optional:** [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) engine (thanks to [@AnCry1596](https://github.com/AnCry1596)): put it + `mp4decrypt` in `bin/`, set `"use_n_m3u8dl_re": true`. Logs (auto-redacted) are in `%LOCALAPPDATA%\crunchyroller\logs` / `~/.config/crunchyroller/logs` / `~/Library/Logs/crunchyroller`.

## <picture><source media="(prefers-color-scheme: dark)" srcset="readme-assets/icon-globe-dark.svg"><img width="22" src="readme-assets/icon-globe-light.svg" alt=""></picture> Community

- [crunchyroller-docker](https://github.com/CatChow0/crunchyroller-docker): run Crunchyroller in Docker, handy for servers and NAS. Thanks [@CatChow0](https://github.com/CatChow0)!

---

<div align="center" markdown="1">
<sub>For personal backup and educational purposes only. Support the official creators with an active Crunchyroll subscription.</sub>
</div>
