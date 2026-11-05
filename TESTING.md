# Validation and acceptance checks

## Recorded development result — 2026-11-05

- Python 3.12.16: **35 backend tests passed**, one live integration test skipped deliberately.
- TypeScript check and Vite production build passed; **2 Vitest tests passed**.
- **4 Playwright checks passed**, covering desktop and phone-sized Chromium layouts and authentication feedback.
- Real localhost app smoke passed: login, SSE dashboard, chunked import, exact imported bytes and queue remaining paused.
- Alembic upgraded a fresh database and reported `0001 (head)`; idempotent migration has automated coverage.
- npm audit reported **0 vulnerabilities** after updating the test runner.
- One dependency deprecation warning remains: Starlette recommends its newer HTTP test-client package; current tests pass using httpx.

These results do not certify long-running production operation or physical iPhone compatibility.

## Automated suites

```powershell
.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Backend tests use synthetic bytes in temporary directories and mock YouTube. They cover stable discovery, Unicode paths, recursive limits, exclusions, modified/moved duplicate files, missing drives, original-byte chunks, saved-session recovery, expired-session blocking, upload/playlist separation, processing state, claim exclusion, schedules, quota errors, token refresh, playlist marker reuse, import offset recovery, CSRF, host validation and login limits.

Playwright uses mocked API responses for desktop and phone-sized Chromium UI checks. `scripts/smoke_server.py` plus `node frontend/e2e/live-smoke.mjs` (run the latter from `frontend`) tests the real FastAPI backend, sign-in, SSE, and local file transfer in isolated `data/smoke`. The queue remains paused; no YouTube request is sent. Screenshots are saved to ignored `data/screenshots`.

On the development machine, sandbox restrictions blocked asyncio loopback sockets and temporary-file renames. The complete suite was therefore run outside that sandbox with approval. Tests must not be interpreted as successful real Google/iPhone integration.

## Opt-in real YouTube integration

**Do not run this without intentionally authorizing a real private upload.** First complete Google setup and connect your channel using the app. Place one tiny valid video (under 10 MiB) in a dedicated directory, then:

```powershell
$env:TUBEVAULT_ALLOW_LIVE_UPLOAD='I_AUTHORIZE_ONE_PRIVATE_TEST_UPLOAD'
$env:TUBEVAULT_LIVE_VIDEO='D:\TubeVault-test\tiny.mp4'
.venv\Scripts\python.exe -m pytest tests/test_live_integration.py -m integration -v
Remove-Item Env:TUBEVAULT_ALLOW_LIVE_UPLOAD
Remove-Item Env:TUBEVAULT_LIVE_VIDEO
```

The test persists its own history in `data/live-integration`, waits up to ten minutes for processing and verifies playlist membership. It never deletes its remote video/playlist. Re-running reuses history. It is skipped by default and was **not run live during development**.

## Manual release gate

Before treating this as an unattended archive, verify:

1. A real ACTION Camera tree maps correctly; root files go to Unsorted; identical names in separate parent roots remain distinguishable. Preview and exclude before starting.
2. A tiny private video completes OAuth → upload → processing → playlist → dashboard. Confirm the actual channel and privacy in YouTube Studio.
3. Interrupt Wi-Fi mid-upload, restore it and confirm only one video is created. Kill the app during a chunk; restart and confirm server-probed continuation. Repeat with PC restart and a multi-GB source.
4. Simulate a lost final response; reconcile uncertain jobs rather than force-uploading. Confirm an expired session blocks safely.
5. Change playlist title in YouTube, rename a local child folder and rescan; the mapping ID must remain stable on the same filesystem. Cross-volume moves receive a new folder identity but content deduplication still applies.
6. Confirm metered-network detection and scheduled hours on this Windows adapter/timezone. Verify the Task Scheduler job after signing out/in.
7. On physical iPhone 13 Safari, test original MOV/HEVC media, phone lock, backgrounding, Wi-Fi dropout, same-file resume, and HTTPS certificate trust. Check imported SHA-256 against the exported original on the PC.
8. Restore a database backup to a separate data directory and confirm history. Never test restore by overwriting your only database.

## Known limits / further hardening

- Live Google integration, actual PC power loss, long-running 4K uploads, physical Safari and Task Scheduler sign-in execution require user-controlled testing.
- Container signature checks are not a full demux/codec validation; Google may reject an unsupported/corrupt file even with a supported extension.
- Default single-worker ordering is deterministic; parallel uploads append in completion order. Recording-date extraction from embedded camera metadata is not implemented; date sorting uses filesystem modification time.
- Dashboard snapshots currently show up to 2,000 jobs/instances and 100 recent events. Larger histories need paginated browsing; the database retains all rows.
- No automatic deletion or retention policy UI is implemented. Completed mobile temporary hardlinks remain until deliberate cleanup. No native iOS app, device-specific roles or Windows toast notifications are included; notifications are persisted in the application database.
- Watch removal disables future scanning rather than deleting history. Disable/enable does not cancel already queued jobs; exclude those explicitly if needed.
- Interrupted playlist creation is reconciled using the durable description marker. A persisted creation intent prevents a second create if Google listing visibility is delayed; select the existing playlist ID manually if it remains ambiguous.
- An uncertain upload with no discoverable remote video stays blocked. Resetting such a job is intentionally not an automatic retry path.
- YouTube's API has no checksum proof that remote media equals your source and YouTube processing is lossy. The stored checksum proves the local identity; it is not a guarantee of byte-perfect recovery from YouTube.
