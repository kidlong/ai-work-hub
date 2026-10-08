# AI Work Hub — App Flutter

Xem hướng dẫn đầy đủ ở [README gốc](../README.md).

```bash
flutter pub get
flutter test
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

Yêu cầu: Flutter 3.47+ (Dart 3.13), Android compileSdk 36 (desugaring đã bật), iOS 13+.
Đã cấu hình sẵn: quyền thông báo + receiver lịch nhắc (Android), `FlutterFragmentActivity` cho sinh trắc học,
`NSFaceIDUsageDescription` và delegate thông báo (iOS).
