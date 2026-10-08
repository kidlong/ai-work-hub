// Contract test: parse đúng các response thật được ghi lại từ backend (mock mode).
import 'dart:convert';
import 'dart:io';

import 'package:ai_work_hub/domain/models.dart';
import 'package:flutter_test/flutter_test.dart';

dynamic fixture(String name) => jsonDecode(File('test/fixtures/$name.json').readAsStringSync());

void main() {
  test('TodayData', () {
    final d = TodayData.fromJson(fixture('today') as Map<String, dynamic>);
    expect(d.user.displayName, 'Nguyễn Văn An');
    expect(d.user.initials, 'VA');
    expect(d.topPriorities, isNotEmpty);
    expect(d.topPriorities.first.score, greaterThan(0));
    expect(d.stats.containsKey('sla_breached'), isTrue);
    expect(d.insights.meetingCount, greaterThan(0));
  });

  test('DailyBrief', () {
    final b = DailyBrief.fromJson(fixture('brief') as Map<String, dynamic>);
    expect(b.headline, startsWith('Hôm nay bạn có'));
    expect(b.topPriorities.length, 3);
    expect(b.schedule, isNotEmpty);
    expect(b.byAi, isFalse);
  });

  test('MeetingPrep', () {
    final p = MeetingPrep.fromJson(fixture('prep') as Map<String, dynamic>);
    expect(p.title, contains('CAB'));
    expect(p.related.map((r) => r.title).join(' '), contains('CORE-2481'));
    expect(p.talkingPoints, isNotEmpty);
  });

  test('Alerts, Ask, Settings, Sources', () {
    final alerts = (fixture('alerts') as List).map((e) => AlertModel.fromJson(e as Map<String, dynamic>)).toList();
    expect(alerts, isNotEmpty);
    expect(alerts.every((a) => ['info', 'warning', 'critical'].contains(a.severity)), isTrue);

    final ask = AskResult.fromJson(fixture('ask') as Map<String, dynamic>);
    expect(ask.items, isNotEmpty);

    final s = UserSettings.fromJson(fixture('settings') as Map<String, dynamic>);
    expect(UserSettings.fromJson(s.toJson()).briefTime, s.briefTime);
    expect(s.copyWith(meetingLeadMinutes: 30).meetingLeadMinutes, 30);

    final src = (fixture('sources') as List).map((e) => SourceInfo.fromJson(e as Map<String, dynamic>)).toList();
    expect(src.map((e) => e.id), contains('sdp'));
  });

  test('WorkItem.isOverdue và keyTime', () {
    final now = DateTime(2026, 10, 8, 10);
    final item = WorkItem.fromJson({
      'id': 1, 'source': 'jira', 'kind': 'task', 'title': 'x',
      'due_at': now.subtract(const Duration(hours: 1)).toUtc().toIso8601String(),
    });
    expect(item.isOverdue(now), isTrue);
    expect(item.keyTime, item.dueAt);
  });
}
