# Install TubeVault from Windows

## Configure the package

1. On the iPhone open Settings → General → About and check iOS Version. TubeVault targets iOS 16+. Verify the chosen installer's current support for that exact version.
2. Open [PR 5](https://github.com/abdullah-al-tamim/TubeVault/pull/5), then Checks → TubeVault iOS → Details. Open the run summary and download **TubeVault-unsigned** under Artifacts while signed in to GitHub. Extract the downloaded ZIP once. Keep TubeVault.ipa intact.
3. Follow [Google setup](ios-google-oauth.md) to obtain your public iOS client ID. Download [configure_ipa.py](../mobile/ios/configure_ipa.py) from the same branch and place it next to the IPA. In that folder open PowerShell and run the following, substituting your client ID and registered bundle ID. The helper creates a new file and refuses to overwrite an existing one.

```powershell
python .\configure_ipa.py .\TubeVault.ipa --client "YOUR_ID.apps.googleusercontent.com" --bundle "com.abdullahaltamim.tubevault"
```

For a build already configured with your client, use TubeVault.ipa directly. An unconfigured build can open and stage local files, but connecting Google requires personalization.

## Install on your iPhone 13 running iOS 27

For this phone use **Sideloadly for Windows**. Its publisher explicitly lists iOS 27 support. It signs TubeVault as a standalone app with your free Apple account. The signing/launch sequence still needs verification on your phone.

1. Download the 64-bit Windows installer from [Sideloadly](https://sideloadly.io/) and follow its Apple device driver prerequisites. Plug the unlocked iPhone into the PC, tap Trust, enter the phone passcode, and select your iPhone in Sideloadly.
2. Drop **TubeVault-personal.ipa** onto the IPA field. Choose Apple ID sideload signing and keep the bundle identifier equal to your iOS OAuth registration. Use the same identifier for each update. Enter Apple account credentials and complete any two-factor prompt in the local installer.
3. Click **Start**. When signing and installation finish, open Settings → General → VPN & Device Management on your iPhone and trust the developer account if prompted. Enable Settings → Privacy & Security → Developer Mode and confirm after restart.
4. Launch TubeVault from the Home Screen, then Settings → Connect Google account. Check the channel ID before queuing a short private test video.
5. Enable Sideloadly automatic refresh and keep the Windows refresh service reachable by the phone before each free seven-day profile expires. You can also reinstall the personalized IPA over the existing app. Keep the same account and bundle ID to preserve the queue.

If Windows cannot see the phone, check USB pairing before troubleshooting signing. If iOS rejects the provisioning profile, record the exact iOS point version and installer error. If Google sign-in fails after successful launch, check the effective signed bundle identifier against your Google iOS credential.

## Alternative installation with AltStore Classic

1. Follow [AltStore's Windows setup](https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows). Use the linked Apple versions of iTunes and iCloud, install AltServer for Windows, then start it. Allow its local-network firewall prompt for your private network.
2. Connect the unlocked iPhone by USB, tap **Trust** on the phone, open iTunes, select the phone, enable **Sync with this iPhone over Wi-Fi** and click Apply.
3. From the AltServer tray icon choose **Install AltStore** and select the iPhone. Enter your Apple Account credentials only in the installer's local prompt.
4. On the phone open Settings → General → VPN & Device Management → Developer App, select your account and trust it. On iOS 16+ enable Settings → Privacy & Security → Developer Mode, restart and confirm when prompted.
5. Transfer TubeVault-personal.ipa to iPhone Files using iCloud Drive or an existing file transfer. With AltServer running on the same network, open AltStore Classic → My Apps → **+**, select the IPA and wait for TubeVault to appear on the Home Screen.
6. Open TubeVault → Settings → Connect Google account. Confirm the channel. For a deliberate end-to-end test, choose a short video you own, set Private, queue it, then explicitly tap Start upload. Check its ID in Archive and visibility in YouTube Studio.
7. In AltStore → My Apps use **Refresh All** before seven days elapse. Keep the PC running AltServer and reachable by USB or local Wi-Fi for refresh. To update, install the new personalized IPA over the existing app with the same Apple account and bundle identity. Deleting the app removes its sandbox queue and staged files.

## Installer choices and troubleshooting

| Method | Role for this build |
| --- | --- |
| [Sideloadly](https://sideloadly.io/) | Preferred for this iOS 27 phone. Direct Windows signing and refresh. |
| [AltStore Classic](https://github.com/altstoreio/AltStore) | Alternative. Windows-assisted personal signing and a standalone Home Screen app. |
| [SideStore](https://docs.sidestore.io/docs/installation/install.html) | Alternative standalone installation with different pairing and refresh requirements. Check its current version-specific instructions. |
| [LiveContainer](https://github.com/LiveContainer/LiveContainer) | Hosts guest apps inside a container. TubeVault depends on its registered callback and background-session relaunch as a standalone app. Guest execution is outside this build's validation. |

If AltServer cannot find the phone, unlock it, reconnect by USB and verify that iTunes recognizes it. If launch reports an untrusted developer, check device trust and Developer Mode. If the free profile expired, refresh or reinstall with the same identity before considering removal. If Google rejects the app, compare the signed bundle ID to the iOS client's registered ID and rebuild the personalized package.

The app uses standard Photos permission, document picker, app-specific Keychain and background URLSession. It requests no push, shared app-group or extension entitlement. The actual signing identity, callback, Keychain continuity, background relaunch and device support still require testing with the signed app.
