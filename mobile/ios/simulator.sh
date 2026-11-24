#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
device=$(xcrun simctl list devices available -j | python3 -c 'import sys,json; print(next(d["udid"] for v in json.load(sys.stdin)["devices"].values() for d in v if d["name"].startswith("iPhone")))')
xcrun simctl boot "$device"
xcrun simctl bootstatus "$device" -b
out=build/simulator/TubeVault.app
mkdir -p "$out"
cp build/Payload/TubeVault.app/Info.plist "$out/"
/usr/libexec/PlistBuddy -c 'Set :CFBundleSupportedPlatforms:0 iPhoneSimulator' "$out/Info.plist"
xcrun --sdk iphonesimulator swiftc -parse-as-library -swift-version 5 -D TUBEVAULT_CHECKS -target "$(uname -m)-apple-ios16.0-simulator" -sdk "$(xcrun --sdk iphonesimulator --show-sdk-path)" Core/*.swift App/*.swift -o "$out/TubeVault"
codesign --force --sign - "$out"
bundle=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$out/Info.plist")
xcrun simctl install "$device" "$out"
xcrun simctl launch "$device" "$bundle"
result="$(xcrun simctl get_app_container "$device" "$bundle" data)/Documents/checks.txt"
for i in {1..60}; do
    if test -f "$result"; then cat "$result"; grep -qx passed "$result"; exit; fi
    sleep 1
done
exit 1
