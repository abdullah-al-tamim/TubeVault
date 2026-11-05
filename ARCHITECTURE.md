# Architecture and decisions

TubeVault is one Windows user process: FastAPI serves a compiled React app, authenticated REST and SSE; a scheduler runs bounded background work. SQLite WAL contains durable identities, instances, mappings, jobs, resumable sessions and audit records. Alembic owns schema changes. A process lock prevents two schedulers using one database. Workers claim jobs transactionally; network operations never hold a SQLite write transaction.

Original bytes are read in bounded chunks. Full SHA-256 is the conservative content identity; sample fingerprints accelerate inspection but never establish equality. Stable size/mtime observations must span the configured delay. Source identity is rechecked before each chunk and full hash before initiation/recovery. In-place changes abort the job. Directory filesystem identities preserve mappings across same-volume renames. Missing sources remain in history.

Upload acceptance, processing and playlist membership are separate durable facts. Session URLs are secrets stored in Windows Credential Manager. A crash reclaims jobs after the single-process lock is acquired. An existing session is probed before any data is retransmitted. Expired or ambiguous sessions enter UPLOAD_UNCERTAIN and require reconciliation with a known video ID; automatic fresh uploads are prohibited. Playlist creation uses a unique durable marker; insertion is reconciled by listing existing membership. Remote title changes never invalidate an ID mapping.

The queue defaults to manual and paused. Automatic/scheduled modes are opt-in. Times use a configurable IANA timezone. Quota/channel-limit errors establish a global cooldown. Concurrency is bounded; scans and playlist changes are serialized. File watching accelerates periodic full reconciliation, which remains authoritative.

Security: all API requests require an HttpOnly session (including localhost), mutation requests require CSRF and an allowed Origin. Login is rate limited. LAN access requires deliberate host/origin configuration and HTTPS termination for confidentiality. Mobile chunks use server-owned transfer IDs, bounded offsets, exclusive destination creation, durable progress, and no user-controlled paths. Imports are never automatically deleted.

## Official documentation checked 2026-11-05

- https://developers.google.com/youtube/data/reference/rest/v3/videos/insert — explicit privacy, 256 GB limit; current reference says 100 calls/day in a separate upload bucket and no private-only restriction for unverified projects. Older revision history differs; check the actual project's console and policy at deployment.
- https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits — default 100 uploads, 100 searches, 10,000 units for other endpoints. No quota bypass.
- https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol — persist URI, probe with empty PUT, 308 Range acknowledgment, 404 expiration.
- https://developers.google.com/identity/protocols/oauth2/native-app — installed desktop client, system browser, loopback callback, PKCE.
- https://developers.google.com/identity/protocols/oauth2/ — testing-mode refresh tokens generally expire after seven days.

Use youtube.force-ssl scope because upload, owned-channel inspection and playlist management are all required. The narrower upload-only scope cannot manage playlists. Credentials must be supplied by the user; consent and verification cannot be automated away.
