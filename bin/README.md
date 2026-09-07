# bin/

Place the following binaries in this directory:

## N_m3u8DL-RE
- **Download**: https://github.com/nilaoda/N_m3u8DL-RE/releases
- **File**: `N_m3u8DL-RE.exe` (Windows)
- **Purpose**: High-speed DASH/HLS segment downloader with built-in mp4decrypt integration

## mp4decrypt (Bento4)
- **Download**: https://www.bento4.com/downloads/ or https://github.com/axiomatic-systems/Bento4/releases
- **File**: `mp4decrypt.exe` (Windows)
- **Purpose**: CENC decryption of downloaded MP4 segments using Widevine KID:KEY pairs

Both tools must be present for the downloader to work.

## Directory structure
```
D:\Crun\
  bin\
    N_m3u8DL-RE.exe   <- place here
    mp4decrypt.exe    <- place here
  crunchyroll\
    ...
  main.py
```
