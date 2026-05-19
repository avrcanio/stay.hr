# Firebase client config — Hospira (`hr.finestar.hospira`)

Project: **hospira-fc0dc**

These files are downloaded from Firebase and kept here for deployment into the Hospira Flutter app.

| File | Target in Flutter project |
|------|---------------------------|
| `google-services.json` | `android/app/google-services.json` |
| `GoogleService-Info.plist` | `ios/Runner/GoogleService-Info.plist` |

## Flutter setup

1. Copy both files into the paths above.
2. Add dependencies to `pubspec.yaml`:
   ```yaml
   dependencies:
     firebase_core: ^3.0.0
     firebase_messaging: ^15.0.0
   ```
3. Run `flutterfire configure --project=hospira-fc0dc` (generates `lib/firebase_options.dart`), or configure manually.
4. Request notification permissions and obtain the FCM device token for push delivery from the stay.hr backend.

## Refresh configs

If apps are re-registered in Firebase Console, re-download configs via Firebase CLI:

```bash
npx -y firebase-tools@latest apps:sdkconfig ANDROID 1:36948128139:android:9ed5c88af6909c08f8bf8e \
  --project hospira-fc0dc -o firebase/client/google-services.json

npx -y firebase-tools@latest apps:sdkconfig IOS 1:36948128139:ios:d55e00e2fc202771f8bf8e \
  --project hospira-fc0dc -o firebase/client/GoogleService-Info.plist
```
