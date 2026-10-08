import 'package:ai_work_hub/app/theme.dart';
import 'package:ai_work_hub/domain/models.dart';
import 'package:ai_work_hub/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

void main() {
  setUpAll(() => initializeDateFormatting('vi'));

  testWidgets('WorkItemTile hiển thị nguồn, tiêu đề và lý do ưu tiên', (tester) async {
    final item = WorkItem.fromJson({
      'id': 1,
      'source': 'sdp',
      'kind': 'ticket',
      'title': '[SDP#50198] Lỗi hiển thị sao kê PDF',
      'sla_due_at': DateTime.now().subtract(const Duration(minutes: 30)).toUtc().toIso8601String(),
      'bucket': 'critical',
      'score': 88,
      'score_reasons': ['ĐÃ VI PHẠM SLA 30 phút', 'Sự cố (incident)'],
    });
    var tapped = false;
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(Brightness.light),
      home: Scaffold(body: WorkItemTile(item: item, showReasons: true, onTap: () => tapped = true)),
    ));
    expect(find.text('SDP'), findsOneWidget);
    expect(find.textContaining('Lỗi hiển thị sao kê'), findsOneWidget);
    expect(find.text('ĐÃ VI PHẠM SLA 30 phút'), findsOneWidget);
    expect(find.textContaining('quá'), findsOneWidget);
    await tester.tap(find.byType(WorkItemTile));
    expect(tapped, isTrue);
  });

  testWidgets('Theme tối dựng được', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(Brightness.dark),
      home: const Scaffold(body: EmptyState(icon: Icons.inbox, title: 'Trống')),
    ));
    expect(find.text('Trống'), findsOneWidget);
  });
}
