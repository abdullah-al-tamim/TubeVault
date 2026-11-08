# Send videos from iPhone over Wi-Fi

1. Open TubeVault on the PC and choose **iPhone Imports**.
2. Connect the iPhone and PC to the same trusted home network. Ethernet on the PC also works when connected to that router.
3. Under **Receive from iPhone**, select the PC connection and destination collection.
4. Read and check the trusted Wi-Fi option, then click **Start receiving**.
5. Scan the QR code with the iPhone Camera. Open its local link in Safari within ten minutes.
6. Tap **Choose videos**, select your videos, then **Send to PC**.
7. Keep Safari open and the phone awake until the page confirms the videos are saved.
8. Click **Stop receiving** on the PC when finished.

TubeVault stores complete files in its local inbox before queuing them. If the YouTube queue is enabled, it uploads them under the current concurrency, schedule, network and quota settings. If paused, use **Start YouTube queue** on the PC. This also enables existing queued jobs.

## Local copies and interruptions

The receiver copies in 4 MiB chunks and commits the received offset to SQLite. If a copy is interrupted, select the same original files again in the same Safari receiving session and tap Send to PC. Completed imports are checked and deduplicated. After the PC restarts, receiving is disabled and a new QR pairing is required. An unfinished file may need to be copied again after a restart or after Safari clears session storage.

TubeVault preserves the bytes iOS supplies. Photos may convert a video when exporting it depending on your iPhone settings. If camera-original bytes are essential, choose Keep Originals in the relevant iPhone transfer/export settings.

The phone can disconnect once copying is complete. YouTube uploading continues from the PC while it is awake and online. Local originals remain until you explicitly delete eligible files under **Archive History > Free up space**. Successful transfers release their temporary staging hardlink, so later cleanup can reclaim the file's storage.

## Network access

The full TubeVault dashboard remains bound to localhost. Start receiving opens a separate upload-only HTTP server on the selected private IPv4 interface and an automatically chosen port. Each QR invitation has a random single-use secret. A paired phone gets upload access for up to twelve hours or until Stop receiving. It can access only files it created during that session.

HTTP does not encrypt video content or pairing credentials in transit. Use this feature only on a trusted private network. The desktop screen requires explicit acknowledgement before opening the receiver. No Google credentials or dashboard sessions are sent to the phone. Stop receiving revokes its access. Receiving is disabled after app restart.

If Windows requests firewall permission, allow TubeVault only on Private networks. Guest Wi-Fi, VPNs or wireless client isolation may prevent connection. No router port forwarding is needed. This release does not modify firewall rules automatically or install certificates.

## Verification limits

Automated tests cover pairing expiry and replay, upload-only access, chunk resume, original-byte storage, duplicate finishing, immediate queueing, and the desktop/mobile browser flows. Actual iPhone Camera scanning, Safari file export, screen-lock suspension, large real videos and your Windows firewall/network still require a device acceptance test.

The browser import control for files chosen on the PC remains under **Import videos selected on this PC**.
