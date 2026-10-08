/// Cấu hình build-time, truyền qua --dart-define.
///
///   flutter run --dart-define=API_BASE_URL=https://aiworkhub.bank.local/api/v1
///
/// Mặc định trỏ tới backend dev trên máy host khi chạy Android emulator.
class AppConfig {
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000/api/v1',
  );

  /// Múi giờ nghiệp vụ. Lịch nhắc dùng thời điểm tuyệt đối (UTC) nên không phụ thuộc
  /// múi giờ thiết bị; giá trị này chỉ dùng để hiển thị và tính "hôm nay".
  static const businessTimezone = 'Asia/Ho_Chi_Minh';

  /// Tối đa số nhắc cục bộ được lên lịch (iOS giới hạn 64 thông báo chờ).
  static const maxScheduledNotifications = 48;

  /// Tự khoá app (yêu cầu sinh trắc học) khi ở nền quá thời gian này.
  static const autoLockAfter = Duration(minutes: 5);
}
