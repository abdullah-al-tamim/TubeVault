# iPhone 13 imports

The Windows PC must be on and reachable. Both workflows preserve the bytes supplied by iOS; TubeVault does not re-encode them. iOS Photos export/share settings can convert media before TubeVault receives it. Choose **Keep Originals** where available and verify an exported file if exact camera-original bytes are essential.

## A. Dedicated Windows SMB inbox

1. Start TubeVault once so `data\inbox` exists. Create collection subfolders within it.
2. Use Windows folder Properties → Sharing → Advanced Sharing to share **only** `data\inbox` as `TubeVaultInbox`.
3. Grant read/write access to a dedicated password-protected Windows account, not Everyone/Guest. Keep NTFS permissions equally narrow. Do not share the project root, system drive or your full video library.
4. On a trusted private network, enable Windows file/printer sharing only for the Private profile and restrict firewall scope to the local subnet. Never configure router port forwarding or public-profile SMB access.
5. On iPhone: Files → Browse → menu → Connect to Server → `smb://YOUR-PC-NAME/TubeVaultInbox`. Authenticate with the dedicated Windows account.
6. Copy videos into a collection subfolder. TubeVault waits for size/mtime stability, checks the container, hashes and deduplicates, then queues the file. Set a long stability delay for slow SMB copies; incomplete containers may be rejected by YouTube and remain local for inspection.

## B. Authenticated mobile web

The default localhost address is intentionally unreachable from a phone. For LAN use, choose a stable PC LAN IP or hostname and configure `.env` explicitly:

```dotenv
TUBEVAULT_HOST=0.0.0.0
TUBEVAULT_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.20
TUBEVAULT_ORIGINS=http://127.0.0.1:8765,http://localhost:8765,https://192.168.1.20
TUBEVAULT_SECURE_COOKIE=true
```

Use a local HTTPS reverse proxy with a certificate trusted by the iPhone and the exact external HTTPS origin listed above. Proxy to the loopback backend, allow streaming SSE, allow 8 MiB requests, and set sufficient request timeouts. Prefer leaving the backend bound to `127.0.0.1` when using a proxy. Restrict the proxy firewall rule to your trusted Private LAN. TLS certificate provisioning is a manual deployment step; no certificate or firewall rule is installed by this project. Plain HTTP can be used only as a deliberate temporary test on an isolated trusted LAN with `SECURE_COOKIE=false`; it does not protect passwords or footage in transit.

Open the HTTPS address in Safari, sign in, then choose **iPhone Imports**. Choose a collection and multiple original video files. Transfers are sequential 4 MiB chunks. Server progress is durable; retry by selecting the same original file and collection. The browser remembers the transfer ID using filename, size and last-modified metadata. If iOS returns different metadata, the UI may create another import; full SHA-256 deduplication still prevents an automatic duplicate YouTube upload.

Keep Safari foregrounded and the phone awake. iOS may suspend transfers when Safari is closed, the screen locks, memory pressure occurs or the network changes. There is no indefinite background-transfer guarantee. Browser tests use a phone-sized viewport; they do not substitute for real Safari testing.

The server uses safe generated destination prefixes to avoid collisions, never silently overwrites an existing file and retains incoming originals. `.transfers` files are hardlinks to ingested originals on NTFS. Automatic cleanup is intentionally disabled; a retention-policy UI is not yet implemented. Do not delete pending transfers. Completed transfer hardlinks may be removed manually only after checking `INGESTED` state and the destination file; removing a hardlink does not remove the other name.

## Future native iOS client

The authenticated REST interface is shared: `POST /api/imports` creates `{filename, collection, size}`, `GET /api/imports/{id}` returns committed offset, `PUT /api/imports/{id}?offset=N` writes up to 8 MiB, and `POST /api/imports/{id}/finish` verifies ingestion. Cookie sessions and CSRF headers apply. A future native app can implement foreground/background transfer coordination and Keychain session storage without changing file ingestion semantics.
