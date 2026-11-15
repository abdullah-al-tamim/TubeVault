# Windows desktop app

Run `artifacts/TubeVault-Setup-0.3.5.exe` to install for the current Windows user. Python and Node are bundled or unnecessary at runtime. Microsoft Edge WebView2 must be installed. The installer adds Start menu and desktop shortcuts and offers background startup at Windows sign-in.

The first launch opens a four-step guide: Google credentials, channel connection, watch folders, and automatic uploading. The guide is also available from Settings. Credentials are stored in Windows Credential Manager. Each user supplies their own Google Desktop OAuth client; credentials are never bundled in the public app.

Closing the window leaves TubeVault in the system tray. The tray menu can reopen the window, pause/resume uploads, or quit. Starting a second copy reopens the existing window. Startup occurs after Windows sign-in, not before login. The PC must be awake and online for uploading.

Data lives in `%USERPROFILE%\TubeVault\data`, outside Windows package-virtualized AppData. On first upgrade, a stopped legacy vault is copied with its protected credentials. Legacy databases are retained as backups; existing destination vaults are never overwritten. Uninstall preserves the archive database and credentials. The dashboard binds to localhost on a dynamically selected port and uses a short-lived, single-use native login ticket. Automatic uploading requires both a connected channel and an enabled watch folder. Choose “Finish with uploads paused” to explore first.

Google setup requires no billing account. Skip trial and billing prompts. Enable YouTube Data API v3, configure an external consent app, add your account as a test user, create a Desktop app client, and import its downloaded JSON. Testing authorizations may expire after seven days; reconnect when requested. The app displays the connected channel for review before uploads are enabled. Google quota and channel limits still apply.

## Build from source

Use Python 3.12, Node, and Inno Setup 6 from its official vendor. In the repository:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[desktop,build]"
cd frontend
npm ci
npm run build
cd ..
.venv\Scripts\python.exe scripts\make_icon.py
.venv\Scripts\python.exe -m PyInstaller --noconfirm packaging\TubeVault.spec
ISCC.exe packaging\TubeVault.iss
```

The standalone folder is `dist/TubeVault`; the installer is in `artifacts`. Source-mode desktop launch: `.venv\Scripts\python.exe desktop_entry.py`. Use `--data-dir data/desktop-smoke` for isolated manual checks; do not enable startup in a test profile.

Live Google uploads, restart after a real Windows reboot, and long-running background reliability require acceptance testing before relying on this as an unattended archive. Keep independent originals.

## Queue controls

Version 0.3.5 explains deletion prerequisites beside the permanent-delete button: pause the queue, wait for active operations to stop, select originals, and type DELETE ORIGINALS. A Pause queue to enable deletion control is available directly in the review. Disabled buttons use a not-allowed cursor; only an actual review, pause or deletion request is marked busy. During deletion the UI explicitly says it is verifying YouTube copies and local checksums, which can take several minutes for large files. No verification requirement is bypassed.

All three file lists (Upload Queue, Archive History, and Review uploaded originals) have independent live fuzzy search and checkbox filters for source folder, extension, and size band. The queue also supports selecting multiple statuses. Open each filter group to choose options; folder options have their own search. Choices within one group are combined with OR, and different groups and the main search combine with AND. Clear filters restores the full current view. Counts beside options describe the current unfiltered view. Changing a filter clears file selection; the originals review also resets its typed confirmation. Select all shown originals selects only the visible matches, and cleanup submits only visible selected IDs.

Archive History and Upload Queue search filenames, collection names and full source folder paths, ignoring case and allowing small spelling mistakes. Multiple search words can appear in any order. Select individual rows or all shown results, then choose Remove selected and confirm. Changing the search or status filter clears selection so hidden matches cannot be removed accidentally.

Archive removal hides the entry from the default history view. Choose Removed entries to restore it. Completion state, checksums, video IDs and duplicate-prevention evidence are retained, and archive totals still include these verified uploads. Queue removal uses the existing durable hold; choose Removed and Resume to restore it. Neither removal action deletes source footage or YouTube resources. Search currently covers the latest 2,000 jobs supplied by the dashboard snapshot.

Upload Queue displays the concurrency limit (1 by default, up to 4). Select rows or all filtered results to pause, resume, skip, cancel, or remove. Active operations stop after the current request; acknowledged progress and video IDs are retained. These actions never delete source files or YouTube videos. Status filters let you restore skipped, cancelled, and removed items. Their records suppress automatic requeueing. TubeVault automatically checks YouTube for a matching upload record every five minutes when it cannot verify the outcome. It retries setup when the saved record proves transfer did not start. It keeps waiting when a transfer may already have finished and YouTube has yet to confirm it.

Browse videos adds only selected files. Files modified within the last 60 seconds must wait. Duplicate content is reused, and completed videos are not uploaded again. Discovery runs separately from the upload scheduler.

Before every new upload session the connected channel uploads playlist is read, with pagination, and titles are compared after Unicode normalization, case folding and whitespace normalization. Matching titles are held as DUPLICATE_TITLE, not marked complete. Existing sessions resume using their saved URI. The queue also offers Check YouTube for duplicates. A failed title check blocks starting a new session. Title matching is conservative and does not prove identical video content; renamed copies cannot be detected by title alone.

Archive History > Free up space reviews completed local originals. Deletion is permanent and requires a paused queue, a selected list, and typing DELETE ORIGINALS. Each file is checked against the processed YouTube archive and its recorded SHA-256 before removal. YouTube re-encodes videos. Keep a separate copy if you need the original file.

Desktop access recovery uses the native window and Windows account. If a session expires, choose Forgot password? Recover access or tray > Recover access. A new one-use ticket restores the session. Browser-only deployments require the PC owner to reset the local TUBEVAULT_PASSWORD configuration and restart the server.

## Receive from iPhone

Open iPhone Imports, confirm your trusted Wi-Fi, and start receiving. Scan the QR with the iPhone Camera, choose videos in Safari, and tap Send to PC. The optional receiver uses a separate private-interface port with upload-only pairing. It stores full files locally, then immediately queues them under the current upload settings. See IPHONE_SETUP.md for network, HTTP privacy, interruption and device-test details.
