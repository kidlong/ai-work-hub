import 'dart:async';

import 'package:ai_work_hub/core/api_client.dart';
import 'package:ai_work_hub/data/live_events.dart';
import 'package:ai_work_hub/data/providers.dart';
import 'package:ai_work_hub/data/repository.dart';
import 'package:ai_work_hub/domain/models.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

LiveEvent ev(int id, {String title = 'Mail mới', String severity = 'warning'}) => LiveEvent(
      id: id,
      type: 'new_item',
      scenario: 's',
      source: 'exchange_mail',
      severity: severity,
      title: title,
      workItemId: id * 10,
      createdAt: DateTime(2026, 10, 8, 9),
    );

class FakeRepo extends WorkHubRepository {
  FakeRepo(this.responses) : super(Dio());

  final List<Object> responses; // LiveEventsPage hoặc Exception
  final List<int?> sinceArgs = [];
  Completer<void>? gate;

  @override
  Future<LiveEventsPage> liveEvents({int? since}) async {
    sinceArgs.add(since);
    if (gate != null) await gate!.future;
    final r = responses[sinceArgs.length - 1];
    if (r is Exception) throw r;
    return r as LiveEventsPage;
  }
}

ProviderContainer containerWith(FakeRepo repo) {
  final c = ProviderContainer(overrides: [repositoryProvider.overrideWithValue(repo)]);
  addTearDown(c.dispose);
  return c;
}

void main() {
  test('lần poll đầu chỉ lấy con trỏ, không phát lại lịch sử', () async {
    final repo = FakeRepo([LiveEventsPage([ev(1), ev(2)], 2)]);
    final c = containerWith(repo);
    await c.read(liveEventsProvider.notifier).poll();
    final s = c.read(liveEventsProvider);
    expect(repo.sinceArgs, [null]);
    expect(s.batch, isEmpty);
    expect(s.seq, 0);
    expect(s.available, isTrue);
  });

  test('poll tiếp theo gửi con trỏ, công bố lô sự kiện và tiến con trỏ', () async {
    final repo = FakeRepo([
      LiveEventsPage([], 5),
      LiveEventsPage([ev(6), ev(7)], 7),
      LiveEventsPage([], 7),
    ]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    await ctrl.poll();
    var s = c.read(liveEventsProvider);
    expect(s.batch.map((e) => e.id), [6, 7]);
    expect(s.seq, 1);
    await ctrl.poll();
    expect(repo.sinceArgs, [null, 5, 7]);
    s = c.read(liveEventsProvider);
    expect(s.seq, 1, reason: 'không có sự kiện mới thì không đổi seq');
  });

  test('server hạ latest_id (reset / dựng lại DB): app hạ con trỏ và vẫn nhận sự kiện mới', () async {
    final repo = FakeRepo([
      LiveEventsPage([], 10),
      LiveEventsPage([], 3), // latest_id < con trỏ
      LiveEventsPage([ev(4)], 4),
    ]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    await ctrl.poll();
    await ctrl.poll();
    expect(repo.sinceArgs, [null, 10, 3]);
    expect(c.read(liveEventsProvider).batch.map((e) => e.id), [4]);
  });

  test('404: đánh dấu không khả dụng và không gọi lại', () async {
    final repo = FakeRepo([ApiException('Không tìm thấy', 404)]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    expect(c.read(liveEventsProvider).available, isFalse);
    await ctrl.poll();
    expect(repo.sinceArgs.length, 1);
  });

  test('lỗi mạng giãn dần tới 30s rồi về 8s khi thành công', () async {
    final err = ApiException('Không kết nối được máy chủ.');
    final repo = FakeRepo([LiveEventsPage([], 1), err, err, err, err, LiveEventsPage([], 1)]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    expect(ctrl.interval, liveBaseInterval);
    await ctrl.poll();
    final seen = <Duration>[];
    for (var i = 0; i < 4; i++) {
      await ctrl.poll();
      seen.add(ctrl.interval);
    }
    expect(seen, [const Duration(seconds: 16), liveMaxInterval, liveMaxInterval, liveMaxInterval]);
    await ctrl.poll();
    expect(ctrl.interval, liveBaseInterval);
  });

  test('hai poll chồng nhau chỉ gọi server một lần', () async {
    final repo = FakeRepo([LiveEventsPage([], 1)])..gate = Completer<void>();
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    final a = ctrl.poll();
    final b = ctrl.poll();
    repo.gate!.complete();
    await Future.wait([a, b]);
    expect(repo.sinceArgs.length, 1);
  });

  test('reset xoá con trỏ: poll kế tiếp lại gửi since = null', () async {
    final repo = FakeRepo([LiveEventsPage([], 5), LiveEventsPage([], 9)]);
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    await ctrl.poll();
    ctrl.reset();
    expect(c.read(liveEventsProvider).available, isNull);
    await ctrl.poll();
    expect(repo.sinceArgs, [null, null]);
  });

  test('reset khi poll đang bay: phản hồi cũ không ghi vào phiên mới', () async {
    final repo = FakeRepo([LiveEventsPage([ev(5)], 5), LiveEventsPage([], 9)])..gate = Completer<void>();
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    final stale = ctrl.poll(); // người dùng A, đang chờ server
    ctrl.reset(); // A đăng xuất, B đăng nhập ngay
    repo.gate!.complete();
    await stale;
    final s = c.read(liveEventsProvider);
    expect(s.available, isNull);
    expect(s.batch, isEmpty);
    expect(s.seq, 0);
    await ctrl.poll(); // poll đầu của B không bị busy cũ chặn, và không mang con trỏ của A
    expect(repo.sinceArgs, [null, null]);
  });

  testWidgets('stop rồi start khi poll đang bay chỉ giữ một vòng lặp', (tester) async {
    final repo = FakeRepo(List.generate(20, (_) => LiveEventsPage([], 1)))..gate = Completer<void>();
    final c = containerWith(repo);
    final ctrl = c.read(liveEventsProvider.notifier);
    ctrl.start(); // t=0: poll #1 bay (chờ gate)
    ctrl.stop();
    ctrl.start(); // vòng 2: poll bị busy chặn, hẹn timer 8s
    await tester.pump(const Duration(seconds: 4));
    repo.gate!.complete(); // t=4: vòng 1 tỉnh dậy; lỗi cũ sẽ hẹn thêm timer thứ hai (nhịp 12s, 20s, 28s)
    await tester.pump();
    await tester.pump(const Duration(seconds: 20)); // tới t=24
    // Một vòng: poll tại t=0, 8, 16, 24 = 4 lần. Hai vòng (lỗi) thêm t=12, 20 = 6 lần.
    expect(repo.sinceArgs.length, 4);
    ctrl.stop();
  });

  test('liveBannerText', () {
    expect(liveBannerText([]), '');
    expect(liveBannerText([ev(1, title: 'A')]), 'A');
    expect(liveBannerText([ev(1, title: 'A'), ev(2, title: 'B'), ev(3, title: 'C')]), '3 mục mới · C');
  });
}
