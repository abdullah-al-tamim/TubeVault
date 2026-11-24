# Initial release limitations

* Signing and on-device Google consent are personal steps. A generic IPA needs a matching iOS OAuth client configured before signing. A green build verifies compilation and mocked checks; it does not certify a physical phone.
* Queue and archive are local to this installation. The app can list remote playlists and check known video IDs. It does not reconstruct a complete cross-device archive from titles.
* Photo access covers authorized assets. Discovery occurs in the foreground. The app has no Share extension, unrestricted background Photos watcher or push entitlement. Desktop Pull is available in Windows TubeVault.
* Upload acceptance and video processing are distinct. Refresh remote status on demand. The UI reports measurable transferred bytes. Speed and ETA are unavailable.
* A resumed transfer may require storage for its remaining suffix. PhotoKit may need to fetch the original before its size can be checked. Interrupted imports can leave staged files if the process is killed before recording them.
* The staging setting limits imports. iOS can also use space internally for its background file transfer. Manual recovery is necessary when Google cannot supply a valid receipt. A lost session never starts a replacement automatically.
* Archive thumbnails, duration, notifications and a LAN companion are outside the initial feature set. Local archive removal also removes the corresponding local duplicate record. YouTube videos and source files stay intact.
