# TubeVault

A local Windows video archive with a React dashboard, durable SQLite upload queue, YouTube resumable uploads and iPhone imports. Original source files are never transcoded, overwritten or automatically deleted. Uploads and playlists default to **Private**. The queue starts **paused** so you can review discovered files first.

## Run on Windows

**Desktop app:** install `artifacts/TubeVault-Setup-0.3.12.exe`, then open TubeVault from the desktop or Start menu. The first-run guide walks through Google credentials, channel connection, folders and background startup. See [DESKTOP.md](DESKTOP.md) for installation and build instructions.

**Just want to see the UI?** Double-click `Start-Preview.cmd` for an isolated sample-data preview. See [PREVIEW.md](PREVIEW.md). A source checkout needs `npm ci` and `npm run build` in `frontend` first; the preview ZIP already includes that build.

Requirements: Python 3.12+, Node.js 22.12+ recommended, Windows Credential Manager, a Google Cloud Desktop OAuth client, and a YouTube channel. No cloud database or hosting subscription.

```powershell
cd C:\Users\ASUS\Documents\ChatGPT\TubeVault
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Open **http://127.0.0.1:8765**. Sign in with the password chosen during setup. Add `D:\ACTION Camera` (use your actual path), scan, wait for the stability interval, then scan again. Review discovery results and excluded files. Connect YouTube in Settings, review metadata/privacy, then start the queue. Scheduled mode also requires the queue to be enabled.

## What is implemented

- Multiple watch roots, recursive discovery, exclusions, stability delay, container checks and SHA-256 content deduplication.
- Folder identities, durable playlist ID mapping, existing-playlist selection, safe reuse and remote rename tolerance.
- Persisted upload intent and encrypted session URLs; server offset probes after interruption; separate processing and playlist insertion.
- Bounded streaming, retries with jitter, quota cooldown, per-worker bandwidth limits, 1–4 workers, scheduled hours and metered-network gating.
- Authenticated dashboard, CSRF protection, live SSE, dark/light themes, queue controls, metadata edits, history and diagnostics.
- Chunked phone uploads, recoverable offsets, atomic no-overwrite ingestion and an SMB inbox workflow.
- Windows sign-in task, schema migration, database backup utility, mocked backend tests and desktop/mobile browser tests.

## Read before unattended use

This is a new implementation, not a field-proven backup system. Real Google OAuth/upload/processing behavior, long-running multi-GB uploads, power-loss recovery and actual iPhone Safari behavior need the acceptance checks in [TESTING.md](TESTING.md). No real channel uploads were performed during development. Retain independent copies of irreplaceable footage: YouTube is a viewing platform and is not a byte-preserving restore service.

An `UPLOAD_UNCERTAIN` job never silently restarts from zero. Inspect YouTube Studio and reconcile its video ID in the queue; the app verifies channel ownership and the durable job marker. If no matching video exists, leave it blocked pending a deliberate operator decision. This conservative policy avoids duplicate uploads after an ambiguous response.

Duplicate content in another local collection is recorded as skipped; it is not uploaded again or automatically added to the other playlist. Force re-upload is an explicit action on completed history. Default single-worker mode preserves discovery order; with multiple workers, playlist order follows completion order.

## Documentation

- [Windows and Google setup](SETUP_WINDOWS.md)
- [iPhone / SMB / LAN setup](IPHONE_SETUP.md)
- [Architecture and API documentation sources](ARCHITECTURE.md)
- [Security model](SECURITY.md)
- [Tests, validation and remaining limitations](TESTING.md)

Google credentials and footage belong outside Git. The application stores tokens and upload session URLs in the current user's Windows Credential Manager. SQLite history remains under `data/`. Back it up with `.venv\Scripts\python.exe scripts\backup.py`.

## Pull YouTube media for editing

In **Video Pull**, paste a single watch, Shorts or share link and choose the format. Best available preserves the selected YouTube streams and merges separate tracks without re-encoding. MP4 selects H.264 video and compatible audio. A height limit selects the best matching version at or below that limit. Audio choices include the native audio stream, M4A and MP3. Availability depends on the video and what YouTube serves to this PC. A YouTube playback stream can differ from the uploaded camera original.

Windows setup selects the download tools by default. If a pull reports missing tools, open **Repair Video Pull Tools** from Start and retry. For a source install, run `powershell -ExecutionPolicy Bypass -File .\scripts\install-pull-tools.ps1` from the project or installed app folder once, then restart TubeVault. This installs the official yt-dlp CLI, FFmpeg/ffprobe and Deno through WinGet. Keep yt-dlp current with `winget upgrade --id yt-dlp.yt-dlp --exact`.

For a local ChatGPT/Codex edit, provide the link and ask it to run the installed command and import the returned JSON `path` into the timeline. From PowerShell:

```powershell
& "$env:LOCALAPPDATA\Programs\TubeVault\TubeVault-Pull.exe" "https://youtu.be/VIDEO_ID_HERE" --format mp4 --height 1080
```

From a source checkout, use `.\.venv\Scripts\python.exe -m tubevault.pulls` with the same arguments. Omit the format and height for highest available. Use `--format audio` for native audio or `--format mp3` for MP3. Add `--output "D:\Edits\Kuakata\References"` to save the media directly there. A successful command exits with code 0. By default the installed desktop dashboard and command share `%USERPROFILE%\TubeVault\data\pulls`. The server uses its configured data directory. Custom output folders stay outside dashboard history. Completed media sits directly in the output folder as <YouTube title>_tubevault.ext. Unsupported filename characters become underscores and duplicate titles receive a number before _tubevault. Receipts and staging files live under .tubevault. The app organizes completed downloads from older versions on first use. The dashboard lists the latest 100.
