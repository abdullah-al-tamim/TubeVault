# iOS verification

GitHub Actions runs swift test, compiles an arm64 device binary, checks the plist and IPA ZIP, then exercises a separate simulator build. The simulator harness imports a generated local file, detects duplicate bytes, reopens SQLite, simulates lost and known sessions, processes HTTP 308 and final acceptance, and checks that the source survives staging cleanup. Mock Google responses exercise access-token refresh, revoked credentials, channel display data and independent playlist recovery. The package tests cover invalid ranges, remote identifiers, subsequence search and Codable playlist recovery. No Apple credentials, personal footage or live uploads are used by CI.

## Pending device verification

| Test | What to verify on the signed iPhone |
| --- | --- |
| Google consent, revoke, refresh and switch | Correct channel; expired access recovers or prompts. Existing jobs cannot resume under another channel. |
| Photos and iCloud-only original | Select several MOV/MP4 assets. Verify download progress, original byte size and duplicate reporting. |
| Upload and playlist | Explicitly start a short private upload. Verify channel, video ID, privacy and playlist in Studio. Repeat for unlisted by choice. |
| Lock or switch apps | Start a larger file, lock or switch away, then reopen. Compare confirmed bytes and video IDs. |
| Wi-Fi outage and cellular handover | Interrupt Wi-Fi with cellular disabled, then enabled on a new request. Resume using the same session. |
| Suspension, force-quit, reboot | Reopen, unlock, reconcile. Verify existing session or explicit uncertainty. Inspect Studio for duplicates. |
| Expiring token during transfer | Reconnect the original channel, probe and resume. Verify the original job ID. |
| Low space and missing staging | Confirm a recoverable error, intact source and no unintended remote upload. |
| Weekly refresh and app update | Refresh/sign with the same identity. Confirm queue, Keychain and archive continuity. |

Full interactive UI, large-file performance, OAuth consent/refresh and real network behavior require further testing. The simulator integration test does not authenticate with Google or create remote resources.
