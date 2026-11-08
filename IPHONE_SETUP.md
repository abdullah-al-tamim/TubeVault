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

The phone page shows copying speed and transferred bytes separately from PC verification and queue preparation. The phone reads and sends 512 KB at a time. It checks the PC's actual received/saving stage during longer requests, rather than assuming the browser's upload progress means the PC has saved the data. A request times out after 30 seconds and retries up to three times, first checking the PC's committed position so a lost response does not restart the file or append the same bytes twice. If recovery fails, tap Send to PC again to resume within the same receiving session. Folder scans serialize short metadata updates, while unrelated file hashes can run independently of phone imports.

Use **Test connection** on the paired phone page to send a disposable 1 MB sample. This does not save a file or create a YouTube upload. It reports the actual phone-to-PC sample speed, independent of Photos exporting or downloading a video. A fast sample does not guarantee sustained video speed; keep Safari visible during both tests and copies. If the sample is slow, check the local Wi-Fi path and VPNs. If the sample is quick but videos are slow, check whether Photos is preparing a copy or downloading the original from iCloud. Physical iPhone/network throughput still needs testing on the user's devices.

Version 0.3.2 tests simulate disconnects both before and after a chunk commit and verify exact original bytes after recovery. The smaller, memory-backed chunks are a mitigation for the observed Safari transfer stalls, not confirmation of a specific Safari defect. Actual throughput on the physical iPhone remains to be verified. Restarting the PC receiver invalidates the pairing; select the files again after scanning a fresh QR code.
