import '../../domain/models.dart';

/// Một thông báo cục bộ sẽ được lên lịch trên máy.
class PlannedNotification {
  PlannedNotification({required this.id, required this.at, required this.title, required this.body, required this.payload});

  final int id;
  final DateTime at;
  final String title;
  final String body;
  final String payload;

  @override
  String toString() => 'PlannedNotification($id, $at, $title)';
}

const briefNotificationId = 900000001;

/// Tiêu đề trung tính (không lộ nội dung nghiệp vụ trên màn hình khoá).
const _neutralTitle = {
  'meeting_soon': 'Sắp có cuộc họp',
  'due_soon': 'Có việc sắp đến hạn',
  'overdue': 'Có việc đã quá hạn',
  'sla_risk': 'Ticket sắp chạm SLA',
  'sla_breached': 'Ticket đã vi phạm SLA',
  'important_message': 'Có tin nhắn quan trọng',
  'mention': 'Bạn được nhắc tên',
  'conflict': 'Lịch họp bị trùng',
  'overload': 'Lịch hôm nay khá dày',
  'digest': 'Có cập nhật mới',
};

/// Thuần logic (dễ test): chọn các nhắc sắp tới để lên lịch trên máy, giúp nhắc vẫn
/// đổ chuông khi mất kết nối VPN hoặc push không tới.
List<PlannedNotification> planNotifications(
  List<AlertModel> upcoming,
  DateTime now, {
  required bool showDetails,
  required int maxCount,
  String? briefTime,
}) {
  final out = <PlannedNotification>[];
  final future = upcoming.where((a) => a.isActive && a.fireAt.isAfter(now)).toList()
    ..sort((a, b) {
      final t = a.fireAt.compareTo(b.fireAt);
      if (t != 0) return t;
      return _rank(b.severity).compareTo(_rank(a.severity));
    });

  final seen = <int>{};
  for (final a in future) {
    if (!seen.add(a.id)) continue;
    out.add(PlannedNotification(
      id: a.id,
      at: a.fireAt,
      title: showDetails ? a.title : (_neutralTitle[a.kind] ?? 'Nhắc việc mới'),
      body: showDetails ? a.body : 'Mở AI Work Hub để xem chi tiết.',
      payload: a.workItemId != null ? 'item:${a.workItemId}' : 'alerts',
    ));
  }

  final brief = nextBriefTime(now, briefTime);
  final reserved = brief != null ? 1 : 0;
  final capped = out.take(maxCount - reserved).toList();
  if (brief != null) {
    capped.add(PlannedNotification(
      id: briefNotificationId,
      at: brief,
      title: 'Morning Brief',
      body: 'Tóm tắt công việc hôm nay của bạn đã sẵn sàng.',
      payload: 'brief',
    ));
  }
  return capped;
}

int _rank(String severity) => switch (severity) { 'critical' => 2, 'warning' => 1, _ => 0 };

/// Lần Morning Brief tiếp theo (bỏ qua thứ 7, Chủ nhật).
DateTime? nextBriefTime(DateTime now, String? hhmm) {
  if (hhmm == null) return null;
  final parts = hhmm.split(':');
  if (parts.length != 2) return null;
  final h = int.tryParse(parts[0]), m = int.tryParse(parts[1]);
  if (h == null || m == null) return null;
  var t = DateTime(now.year, now.month, now.day, h, m);
  if (!t.isAfter(now)) t = t.add(const Duration(days: 1));
  while (t.weekday == DateTime.saturday || t.weekday == DateTime.sunday) {
    t = t.add(const Duration(days: 1));
  }
  return t;
}
