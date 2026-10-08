import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import '../config.dart';
import 'notification_planner.dart';

/// Lên lịch nhắc việc cục bộ trên thiết bị từ danh sách alert của backend.
class LocalNotifications {
  LocalNotifications._();
  static final instance = LocalNotifications._();

  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;

  /// Được gọi khi người dùng chạm vào thông báo (payload: `item:<id>`, `alerts` hoặc `brief`).
  void Function(String payload)? onTap;
  String? launchPayload;

  static const _channel = AndroidNotificationDetails(
    'work_alerts',
    'Nhắc việc',
    channelDescription: 'Nhắc họp, hạn chót, SLA và tin nhắn quan trọng',
    importance: Importance.high,
    priority: Priority.high,
    visibility: NotificationVisibility.private,
  );

  Future<void> init() async {
    if (_ready || kIsWeb) return;
    tzdata.initializeTimeZones();
    tz.setLocalLocation(tz.getLocation(AppConfig.businessTimezone));
    const settings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      iOS: DarwinInitializationSettings(
        requestAlertPermission: false,
        requestBadgePermission: false,
        requestSoundPermission: false,
      ),
    );
    await _plugin.initialize(
      settings: settings,
      onDidReceiveNotificationResponse: (r) {
        final p = r.payload;
        if (p != null) onTap?.call(p);
      },
    );
    final launch = await _plugin.getNotificationAppLaunchDetails();
    if (launch?.didNotificationLaunchApp ?? false) {
      launchPayload = launch!.notificationResponse?.payload;
    }
    _ready = true;
  }

  Future<void> requestPermission() async {
    if (!_ready) return;
    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    await _plugin
        .resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>()
        ?.requestPermissions(alert: true, badge: true, sound: true);
  }

  /// Thay toàn bộ lịch nhắc cục bộ bằng kế hoạch mới.
  Future<int> apply(List<PlannedNotification> plan) async {
    if (!_ready) return 0;
    await _plugin.cancelAllPendingNotifications();
    const details = NotificationDetails(
      android: _channel,
      iOS: DarwinNotificationDetails(presentAlert: true, presentSound: true),
    );
    var n = 0;
    for (final p in plan) {
      try {
        await _plugin.zonedSchedule(
          id: p.id,
          scheduledDate: tz.TZDateTime.from(p.at, tz.local),
          notificationDetails: details,
          // Không cần quyền exact alarm; sai lệch vài phút chấp nhận được với nhắc trước 15'
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
          title: p.title,
          body: p.body,
          payload: p.payload,
        );
        n++;
      } catch (e) {
        debugPrint('Không lên lịch được nhắc ${p.id}: $e');
      }
    }
    return n;
  }

  Future<void> clear() async {
    if (_ready) await _plugin.cancelAll();
  }
}
