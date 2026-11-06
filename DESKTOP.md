# Windows desktop app

Run `artifacts/TubeVault-Setup-0.2.0.exe` to install for the current Windows user. Python and Node are bundled or unnecessary at runtime. Microsoft Edge WebView2 must be installed. The installer adds Start menu and desktop shortcuts and offers background startup at Windows sign-in.

The first launch opens a four-step guide: Google credentials, channel connection, watch folders, and automatic uploading. The guide is also available from Settings. Credentials are stored in Windows Credential Manager. Each user supplies their own Google Desktop OAuth client; credentials are never bundled in the public app.

Closing the window leaves TubeVault in the system tray. The tray menu can reopen the window, pause/resume uploads, or quit. Starting a second copy reopens the existing window. Startup occurs after Windows sign-in, not before login. The PC must be awake and online for uploading.

Data lives in `%LOCALAPPDATA%\TubeVault\data`. Uninstall preserves the archive database and credentials. The app binds only to localhost on a dynamically selected port and uses a short-lived, single-use native login ticket. Automatic uploading requires both a connected channel and an enabled watch folder. Choose “Finish with uploads paused” to explore first.

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
