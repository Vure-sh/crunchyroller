### What's Changed in v3.7.1

- **Windows Long Path Budgeting (Closes #17)**: Fixed `[Errno 2] No such file or directory` crashes on Windows when downloading shows with very long titles (e.g. *A Livid Lady's Guide to Getting Even...*). Output paths and intermediate muxing files (`.tmp.mkv`) are now dynamically budgeted to stay safely $\le 259$ characters (`MAX_PATH`) while preserving season/episode identifiers (`S01E08`), quality tags, and existing file compatibility.
- **Safe Temporary Chapter Metadata**: Chapter markers during FFmpeg muxing are now written to the system temporary directory (via `tempfile`) instead of appending `.chapters.txt` to the destination filename, preventing path overflow during merge.
- **Connection Pool Expansion**: Increased HTTP connection pool capacities across the session pool, downloader, and worker queues (scaling to 64–128 connections). This eliminates `[urllib3.connectionpool] Connection pool is full` warnings and reduces unnecessary TLS renegotiations under high worker concurrency.

**Full Changelog**: https://github.com/Vure-sh/crunchyroller/compare/v3.7.0...v3.7.1
