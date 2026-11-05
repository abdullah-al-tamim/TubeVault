# Windows setup

1. Install Python 3.12+ with its launcher and a current Node.js LTS (22.12+ recommended). Keep this directory on local NTFS, not a synced folder or network drive.
2. Run `scripts\setup.ps1` from PowerShell. It installs dependencies, compiles the dashboard, asks for a password, creates `.env` if absent, and migrates SQLite. It does not register startup or open a firewall port.
3. Run `scripts\start.ps1`. Open http://127.0.0.1:8765 and sign in. A second instance is refused by the process lock. Do not launch Uvicorn with multiple workers.
4. Add your parent video folder. Choose exclusions, depth, stability delay and privacy. Watch removal is implemented as disabling, so history and mappings remain intact. Newly added watch paths receive periodic scans immediately; restart to attach their Watchdog observers.
5. The queue starts paused. Scan twice with at least the stability interval between scans, inspect the discovery preview, edit metadata/exclude unwanted jobs, then enable uploads.

## Google Cloud configuration (manual)

1. Create/select your personal project in https://console.cloud.google.com/. Enable **YouTube Data API v3**.
2. Configure the OAuth consent screen, choose External if appropriate, and add your Google account as a test user while in Testing.
3. Create an OAuth client of application type **Desktop app**. Download its JSON into `data/client_secret.json`. Do not paste it into chat or commit it.
4. In TubeVault Settings choose Connect / reconnect from the Windows PC. The system browser opens Google's consent screen; choose the account/channel you intend to archive to. The callback uses an ephemeral loopback port and PKCE.
5. TubeVault requests `youtube.force-ssl` for uploads, channel inspection and playlist management. Google may describe broader capabilities covered by that scope; TubeVault never automatically deletes remote videos or playlists.
6. Check the displayed channel name and ID. A different channel is rejected once the data directory is associated with a channel. Use a separate data directory for a different channel.

Testing-mode refresh tokens generally expire after seven days; reconnect when required. Production consent publishing, verification or quota audits must follow Google's current requirements. Current API documentation checked on 2026-11-05 lists 100 default daily video-upload calls in a separate bucket and no private-only restriction for unverified projects; older documentation differs. Your project's console and returned API errors are authoritative. TubeVault always sends explicit privacy and never bypasses restrictions. Quota/channel-limit errors hold the queue for 24 hours rather than guessing a reset time.

## Automatic startup and operation

After verifying manual launch, run `scripts\register-startup.ps1`. It registers a current-user, limited-privilege task at Windows sign-in, using `pythonw.exe` and this repository as working directory. It restarts on failure and refuses parallel task instances. Credential Manager access requires the same Windows user. To remove it, run `scripts\register-startup.ps1 -Remove`.

Windows sleep, power loss and shutdown interrupt uploads. On startup, jobs reclaim local claims and probe saved server sessions. Keep the PC awake during upload windows using Windows power settings. No promise is made that uploads run while the PC is off. Metered-network detection uses the Windows connection-cost API; unknown cost pauses when that option is enabled. Disable that setting deliberately if your network adapter does not expose cost information.

To stop interactively, press Ctrl+C. The worker finishes or times out its current bounded network request, then exits. Task Scheduler termination may be abrupt; durable session probing is the recovery path.

## Backups and updates

Run `.venv\Scripts\python.exe scripts\backup.py` for a consistent SQLite snapshot. Copy snapshots to independent storage. Keep source footage backed up separately. Credential Manager secrets are tied to the Windows user; copying the database alone does not copy upload-session credentials. Missing session credentials block uncertain uploads. Reconnect Google after migrating Windows accounts.

Before updates: pause queue, stop app, back up database, update code, reinstall dependencies/build frontend, then run startup (which executes Alembic). Never downgrade by dropping tables.

## GitHub

The available GitHub connector does not expose repository creation, and GitHub CLI was not installed during development. Local commits are provided. To publish privately after installing/authenticating `gh`:

```powershell
gh auth login
gh repo create tubevault --private --source . --remote origin --push
```

Review `git status` first; ignored `data/`, `.env`, tokens and footage must remain untracked.
