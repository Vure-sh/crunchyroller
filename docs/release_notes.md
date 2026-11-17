### What's Changed in v3.8.1

- **Audio Language Fallback Setting (Addresses #22)**:
  - Added a dedicated toggle in Settings (`audio language fallback`, enabled by default) and CLI flag (`--audio-fallback` / `--no-audio-fallback`).
  - Keeps the logical fallback to original audio (Japanese) enabled by default so downloads don't fail when a dub is unavailable.
  - When turned off, episodes lacking the requested dub are cleanly skipped without halting the download queue or failing the batch.
- **Dual-Track Subtitles on Dub Downloads**:
  - Fixed an issue where downloading foreign audio (e.g. French, German dubs) only included Signs & Songs tracks, leaving spoken dialogue without subtitles.
  - Automatically fetches the full dialogue subtitle catalog from the original/master stream while preserving the dub's native Signs & Songs (forced narrative) track.
  - Automatically sets default disposition for dialogue tracks so subtitles appear by default during speech across VLC, MPV, Plex, and Jellyfin, with cleanly labeled tracks (e.g. `Français` and `Français [Signs & Songs]`).
- **Subtitle Pipeline Overhaul (Fixes #20)**:
  - Prioritized official Web playback endpoint (`web/chrome/play`) for comprehensive multi-language `.ass` soft subtitle catalog retrieval, replacing empty/stub Android TV stream responses.
  - Multi-language alias resolution supporting 2-letter, 3-letter (ISO-639-2), and localized naming (`fra`, `fre`, `french`, `deu`, `ger`, `german`, `spa`, `spanish`, etc.).
  - Bearer authentication injection for protected CDN subtitle segment downloads.
  - Resolved relative DASH MPD `AdaptationSet` `BaseURL` tracks with manifest URLs.
- **Auth & Session Token Lifecycle Resilience**:
  - Proactively refreshes expired Android TV access tokens before dispatching requests.
  - Intercepts HTTP 403 Forbidden playback errors alongside HTTP 401, automatically refreshing tokens and retrying requests without failing downloads.
  - Clean auth state synchronization when logging in with `etp_rt` or credentials, purging stale credentials to eliminate dead token shadowing.
  - Resilient catalog search with automatic fallback to guest token if user session has expired.

### What's Changed in v3.8.0

- **Recently Added Anime Catalog (#18)**: Added a new "recently added" catalog tab powered by Crunchyroll's Browse API, allowing instant exploration of the latest anime additions with poster artwork, episode counts, audio languages, and descriptions.
- **Dynamic Catalog Search & Filter**: Real-time anime filtering directly within the top header with embedded catalog count indicator.
- **Batch Selection & Dual Actions**: Multi-select cards to either fetch entire series into your Dashboard episode tree or trigger instant batch queueing.
- **Multi-Language Subtitle Preservation**: Fixed an issue where upgrading to the high-speed mobile `/download` CDN profile dropped non-English subtitle tracks (`fr-FR`, `de-DE`, `es-419`, `it-IT`, etc.). Standard and mobile subtitle dictionaries are now cleanly merged.
- **Candidate Dub Version Prioritization**: Candidate dub versions now prioritize matching the user's requested subtitle locales first, ensuring dialogue subtitles are not skipped.
- **64-bit Clipboard Safety (Fixes #19)**: Resolved silent application crashes on Windows 64-bit when pasting URLs via the context menu by properly declaring ctypes Win32 API pointer types and adding mutex retry handling.
- **Standalone Distribution Optimization**: Removed unused binaries and unneeded package bloat from release bundles.

**Full Changelog**: https://github.com/Vure-sh/crunchyroller/compare/v3.7.1...v3.8.0
