#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
device=$(xcrun simctl list devices available -j | python3 -c 'import sys,json; print(next(d["udid"] for v in json.load(sys.stdin)["devices"].values() for d in v if d["name"].startswith("iPhone")))')
echo "Booting the iPhone simulator"
xcrun simctl boot "$device"
xcrun simctl bootstatus "$device" -b
out=build/simulator/TubeVault.app
mkdir -p "$out"
cp build/Payload/TubeVault.app/Info.plist "$out/"
/usr/libexec/PlistBuddy -c 'Set :CFBundleSupportedPlatforms:0 iPhoneSimulator' "$out/Info.plist"
xcrun --sdk iphonesimulator swiftc -parse-as-library -swift-version 5 -D TUBEVAULT_CHECKS -target "$(uname -m)-apple-ios16.0-simulator" -sdk "$(xcrun --sdk iphonesimulator --show-sdk-path)" Core/*.swift App/*.swift -o "$out/TubeVault"
cat > build/sim-entitlements.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict><key>application-identifier</key><string>LOCALTEST.com.abdullahaltamim.tubevault</string><key>keychain-access-groups</key><array><string>LOCALTEST.com.abdullahaltamim.tubevault</string></array></dict></plist>
PLIST
codesign --force --sign - --entitlements build/sim-entitlements.plist "$out"
bundle=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$out/Info.plist")
echo "Installing simulator build"
xcrun simctl install "$device" "$out"
echo "Launching queue checks"
xcrun simctl launch "$device" "$bundle"
echo "Checking persistent test result"
result="$(xcrun simctl get_app_container "$device" "$bundle" data)/Documents/checks.txt"
for i in {1..60}; do
    if test -f "$result"; then cat "$result"; grep -qx passed "$result"; exit; fi
    sleep 1
done
exit 1
