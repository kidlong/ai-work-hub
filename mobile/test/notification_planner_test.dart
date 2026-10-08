import 'package:ai_work_hub/core/notifications/notification_planner.dart';
import 'package:ai_work_hub/domain/models.dart';
import 'package:flutter_test/flutter_test.dart';

AlertModel alert(int id, DateTime at, {String kind = 'meeting_soon', String severity = 'info', String status = 'pending', int? item}) =>
    AlertModel(id: id, workItemId: item, kind: kind, severity: severity, title: 'Họp CAB lúc 09:30', body: 'Phòng 1203', fireAt: at, status: status);

void main() {
  final now = DateTime(2026, 10, 8, 8, 0); // Thứ Năm

  test('chỉ lên lịch nhắc tương lai, còn hiệu lực, sắp theo thời gian', () {
    final plan = planNotifications([
      alert(1, now.add(const Duration(hours: 2))),
      alert(2, now.subtract(const Duration(minutes: 1))),
      alert(3, now.add(const Duration(minutes: 30)), item: 9),
      alert(4, now.add(const Duration(hours: 1)), status: 'acked'),
    ], now, showDetails: true, maxCount: 10);
    expect(plan.map((p) => p.id), [3, 1]);
    expect(plan.first.payload, 'item:9');
    expect(plan.last.payload, 'alerts');
  });

  test('mặc định ẩn nội dung nghiệp vụ trên màn hình khoá', () {
    final p = planNotifications([alert(1, now.add(const Duration(hours: 1)), kind: 'sla_breached')], now,
        showDetails: false, maxCount: 10).single;
    expect(p.title, 'Ticket đã vi phạm SLA');
    expect(p.body, isNot(contains('1203')));
  });

  test('giới hạn số lượng và giữ chỗ cho Morning Brief', () {
    final alerts = [for (var i = 0; i < 100; i++) alert(i, now.add(Duration(minutes: i + 1)))];
    final plan = planNotifications(alerts, now, showDetails: true, maxCount: 48, briefTime: '07:30');
    expect(plan.length, 48);
    expect(plan.last.id, briefNotificationId);
  });

  test('Morning Brief bỏ qua cuối tuần', () {
    final friEvening = DateTime(2026, 10, 9, 18, 0);
    expect(nextBriefTime(friEvening, '07:30'), DateTime(2026, 10, 12, 7, 30)); // Thứ Hai
    expect(nextBriefTime(DateTime(2026, 10, 8, 6, 0), '07:30'), DateTime(2026, 10, 8, 7, 30));
    expect(nextBriefTime(now, 'abc'), isNull);
  });
}
