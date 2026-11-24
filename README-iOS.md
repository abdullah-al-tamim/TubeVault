# TubeVault for iPhone

Standalone SwiftUI app for iPhone 13 running iOS 16 or later. A Windows connection is needed for initial AltStore setup and subsequent signing refreshes. Direct Google uploads use the iPhone's own connection.

1. [Install on Windows and iPhone](docs/ios-install-windows.md).
2. [Create the Google iOS client](docs/ios-google-oauth.md).
3. In Settings connect the YouTube channel. Choose private or unlisted visibility and an optional playlist.
4. In Add Videos choose Files or scan permitted Photos videos. Open a queued item, check the destination and tap Start upload.
5. Open Archive to see the returned video ID, inspect remote status, or retry playlist membership.

[Architecture](docs/ios-architecture.md) · [Background transfers](docs/ios-background-upload.md) · [Testing](docs/ios-testing.md) · [Known limitations](docs/ios-known-limitations.md)

The build workflow compiles for arm64 using Apple's iPhoneOS SDK, packages Payload/TubeVault.app, runs simulator checks and publishes TubeVault-unsigned. For local development on a Mac with full Xcode selected, run `swift test`, `bash build.sh` and `bash simulator.sh` inside mobile/ios. On Windows use the workflow artifact. The app and build helpers use platform frameworks and the Python standard library. Apple signing takes place on the user's machine.
