import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Lưu token và tuỳ chọn bảo mật trong Keychain (iOS) / Keystore (Android).
/// Không lưu mật khẩu người dùng.
class SecureStore {
  SecureStore([FlutterSecureStorage? storage]) : _s = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _s;

  static const _access = 'access_token';
  static const _refresh = 'refresh_token';
  static const _biometric = 'pref_biometric_lock';
  static const _details = 'pref_notification_details';

  Future<String?> get accessToken => _s.read(key: _access);
  Future<String?> get refreshToken => _s.read(key: _refresh);

  Future<void> saveTokens(String access, String refresh) async {
    await _s.write(key: _access, value: access);
    await _s.write(key: _refresh, value: refresh);
  }

  Future<void> clearTokens() async {
    await _s.delete(key: _access);
    await _s.delete(key: _refresh);
  }

  Future<bool> get biometricLock async => (await _s.read(key: _biometric)) == '1';
  Future<void> setBiometricLock(bool v) => _s.write(key: _biometric, value: v ? '1' : '0');

  /// Mặc định KHÔNG hiện nội dung chi tiết trên thông báo (màn hình khoá).
  Future<bool> get notificationDetails async => (await _s.read(key: _details)) == '1';
  Future<void> setNotificationDetails(bool v) => _s.write(key: _details, value: v ? '1' : '0');
}
