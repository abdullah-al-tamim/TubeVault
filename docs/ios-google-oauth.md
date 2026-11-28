# Google setup

1. Open [Google Cloud Console](https://console.cloud.google.com/apis/credentials). Select the project used for the Windows TubeVault client. In APIs & Services → Library enable YouTube Data API v3.
2. Under Google Auth Platform → Audience, if the app is External and in Testing, add the Google account that owns the YouTube channel as a test user. Under Data Access configure https://www.googleapis.com/auth/youtube.force-ssl for uploads, private channel reads and playlist management.
3. Under Clients choose Create client → iOS. Enter the bundle identifier the personal signer will use for TubeVault. The source default is `com.abdullahaltamim.tubevault`. If your signer rewrites it, use the installed identifier when registering the client. Leave the App Store ID blank for personal installation where optional.
4. Copy the public client ID ending in .apps.googleusercontent.com. Run the Windows personalization command in the installation guide. It registers the reversed client ID as a callback scheme and uses the redirect path /oauthredirect. A second option for future builds is to set GitHub repository Actions variables GOOGLE_IOS_CLIENT_ID and IOS_BUNDLE_ID before compiling.
5. On iPhone, open Settings → Connect Google account, complete the browser consent screen, select the channel/account when Google offers a choice, then verify the displayed channel title and ID. To switch, pause transfers, disconnect and reconnect. Existing sessions are bound to the original channel.

For access_denied check test-user membership. For a redirect or client error check iOS client type, exact bundle ID, callback scheme and the IPA you actually installed. If consent has expired, reconnect the same channel. The desktop client configuration file does not provide an iOS client. Personal Apple sign-in takes place only in the installation tool. The app stores Google credentials and session addresses in the device Keychain.

[Google installed-app OAuth](https://developers.google.com/identity/protocols/oauth2/native-app) · [YouTube quotas](https://developers.google.com/youtube/data/guides/quota_and_compliance_audits)
