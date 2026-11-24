# Transfer behavior

The app saves the job intent before requesting a session and places the returned address in the Keychain. It hands a file-backed PUT to a named background URLSession. The first PUT uses the staged original. After interruption, Resume sends a zero-length PUT with Content-Range bytes */total. A valid 308 range selects the confirmed offset. A partial resume stages the remaining suffix on disk. Allow space for that suffix.

The UI separates bytes sent by the device from server-confirmed bytes. An accepted video ID moves the record to Archive. Playlist insertion and processing status are independent of upload acceptance. Jobs with an ambiguous session initiation stop for manual verification against the channel ID and job marker.

Locking or switching apps lets iOS schedule an existing file transfer. Google authorization, initiation, probing, retry timers and playlist work need execution time. Reopen the app to continue a paused job or retry playlist association. System termination can relaunch the app for session events. Swiping it away cancels background work and requires reopening. A charging preference gates initiation. It cannot control when iOS transmits a previously scheduled request.

Mocked callbacks can exercise transition handling. Timing on real Wi-Fi, cellular, battery power and locked-device data protection needs the physical checklist in ios-testing.md.

[Apple background session configuration](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/background(withidentifier:)) · [YouTube resumable uploads](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol)
