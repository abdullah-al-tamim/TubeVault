#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
out=build/Payload/TubeVault.app
mkdir -p "$out"
xcrun --sdk iphoneos swiftc -parse-as-library -swift-version 5 -O -target arm64-apple-ios16.0 -sdk "$(xcrun --sdk iphoneos --show-sdk-path)" Core/*.swift App/*.swift -o "$out/TubeVault"
python3 - <<'PY'
import os, plistlib, re
client = os.environ.get("GOOGLE_IOS_CLIENT_ID", "").strip()
if client and not re.fullmatch(r"[a-zA-Z0-9-]+\.apps\.googleusercontent\.com", client):
    raise ValueError("Invalid iOS OAuth client ID")
bundle = os.environ.get("IOS_BUNDLE_ID") or "com.abdullahaltamim.tubevault"
info = dict(CFBundleExecutable="TubeVault", CFBundleName="TubeVault", CFBundleDisplayName="TubeVault",
    CFBundleIdentifier=bundle, CFBundleVersion="2", CFBundleShortVersionString="0.2.0", CFBundlePackageType="APPL",
    CFBundleInfoDictionaryVersion="6.0", LSRequiresIPhoneOS=True, UIDeviceFamily=[1], MinimumOSVersion="16.0",
    CFBundleSupportedPlatforms=["iPhoneOS"], UILaunchScreen={}, UISupportedInterfaceOrientations=["UIInterfaceOrientationPortrait"],
    NSPhotoLibraryUsageDescription="Select original videos to stage in your private upload queue.",
    GoogleClientID=client)
if client:
    info["CFBundleURLTypes"]=[dict(CFBundleURLSchemes=[".".join(reversed(client.split(".")))])]
with open("build/Payload/TubeVault.app/Info.plist","wb") as f: plistlib.dump(info,f)
PY
plutil -lint "$out/Info.plist"
(cd build && /usr/bin/zip -q -r TubeVault.ipa Payload)
unzip -t build/TubeVault.ipa
