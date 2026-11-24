# Native architecture

The Windows project uses FastAPI, React, SQLite and a Python Google transport. The existing phone interface transfers files to a PC. The new mobile/ios application stages footage and sends it to Google directly. Source files in Core define portable job metadata, validated offsets and fuzzy matching. App contains SwiftUI, a SQLite repository, PhotoKit ingestion, OAuth/YouTube transport, queue orchestration and a URLSession delegate.

SQLite stores a versionable Codable queue snapshot as one transaction, serialized through the main actor. Video bytes use UUID filenames in Application Support, excluded from iCloud backup. SHA-256 of the full staged bytes identifies duplicate imports. The source path is never a cleanup target. Keychain holds credentials and session addresses with after-first-unlock device-only accessibility. No logging of network bodies or credentials is implemented.

The queue defaults to manual initiation and private visibility. A job records channel, requested destination, durable intent, confirmed bytes, accepted video ID and independent playlist state. Authentication uses system browser, PKCE S256, randomized state and a native redirect. Playlist mapping uses exact saved album/folder names scoped to the channel. YouTube resources are identified by ID. Title equality never establishes content identity.

For a future paired desktop protocol, exchange channel ID, video ID, playlist ID, content SHA-256, size and acceptance date. A transport needs explicit authenticated pairing before exposing any local endpoint. Desktop Pull remains in Windows TubeVault.
