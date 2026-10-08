### What's Changed in v3.6.0

- **Audio & Subtitle Only Download Mode (Closes #15)**: Added option to download audio tracks and subtitles without downloading video streams. Available under the Video Quality dropdown (`audio only (no video)`) in the GUI or via `--no-video` / `--audio-only` in CLI. Supports `.mka` container (default), `.mkv`, or standalone `.m4a` with companion subtitle files.
- **Anti-RateLimit Safe Mode & Pacing Controls (Addresses #14)**: Added configurable delay between episode downloads (default 60s, with ±5s jitter) and optional thread reduction to protect against KAT-3002 temporary blocks.
- **Redesigned History View**: Upgraded to a clean two-line layout showing series title, season/episode tags, episode title, quality, relative timestamp, file size, status pill, and a one-click show-in-folder button.
- **Enhanced Progress & Phase Tracking**: Displays live percentage indicators on sub-bars and detailed phase logging.

**Full Changelog**: https://github.com/Vure-sh/crunchyroller/compare/v3.5.1...v3.6.0
