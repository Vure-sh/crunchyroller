### What's Changed in v3.8.0

- **Recently Added Anime Catalog (#18)**: Added a new "recently added" catalog tab powered by Crunchyroll's Browse API, allowing instant exploration of the latest anime additions with poster artwork, episode counts, audio languages, and descriptions.
- **Dynamic Catalog Search & Filter**: Real-time anime filtering directly within the top header with embedded catalog count indicator.
- **Batch Selection & Dual Actions**: Multi-select cards to either fetch entire series into your Dashboard episode tree or trigger instant batch queueing.
- **Multi-Language Subtitle Preservation**: Fixed an issue where upgrading to the high-speed mobile `/download` CDN profile dropped non-English subtitle tracks (`fr-FR`, `de-DE`, `es-419`, `it-IT`, etc.). Standard and mobile subtitle dictionaries are now cleanly merged.
- **Candidate Dub Version Prioritization**: Candidate dub versions now prioritize matching the user's requested subtitle locales first, ensuring dialogue subtitles are not skipped.
- **64-bit Clipboard Safety (Fixes #19)**: Resolved silent application crashes on Windows 64-bit when pasting URLs via the context menu by properly declaring ctypes Win32 API pointer types and adding mutex retry handling.
- **Standalone Distribution Optimization**: Removed unused binaries and unneeded package bloat from release bundles.

**Full Changelog**: https://github.com/Vure-sh/crunchyroller/compare/v3.7.1...v3.8.0
