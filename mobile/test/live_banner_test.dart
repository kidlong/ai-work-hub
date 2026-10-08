import 'package:ai_work_hub/app/app.dart';
import 'package:ai_work_hub/app/router.dart';
import 'package:ai_work_hub/data/live_events.dart';
import 'package:ai_work_hub/data/providers.dart';
import 'package:ai_work_hub/domain/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

class FakeAuth extends AuthController {
  FakeAuth(this.initial);
  final AuthStatus initial;

  @override
  AuthState build() => AuthState(initial);

  void set(AuthStatus s) => state = AuthState(s);
}

class FakeLive extends LiveEventsController {
  @override
  void start() {}
  @override
  void stop() {}
  @override
  void reset() {}

  void push(String title) =>
      state = LiveFeedState(available: true, batch: [_ev(state.seq + 1, title)], seq: state.seq + 1);
}

LiveEvent _ev(int id, String title) => LiveEvent(
      id: id,
      type: 'new_item',
      scenario: 's',
      source: 'exchange_mail',
      severity: 'warning',
      title: title,
      workItemId: id * 10,
      createdAt: DateTime(2026, 10, 8, 9),
    );

class FakeSync extends NotificationSync {
  FakeSync(super.ref);
  @override
  Future<int> resync() async => 0;
}

Future<(ProviderContainer, FakeAuth)> pumpApp(WidgetTester tester, AuthStatus initial) async {
  final auth = FakeAuth(initial);
  final container = ProviderContainer(overrides: [
    authProvider.overrideWith(() => auth),
    liveEventsProvider.overrideWith(FakeLive.new),
    notificationSyncProvider.overrideWith((ref) => FakeSync(ref)),
    routerProvider.overrideWith(
      (ref) => GoRouter(routes: [GoRoute(path: '/', builder: (_, _) => const Scaffold(body: Text('home')))]),
    ),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(container: container, child: const AiWorkHubApp()));
  await tester.pump();
  return (container, auth);
}

FakeLive liveOf(ProviderContainer c) => c.read(liveEventsProvider.notifier) as FakeLive;

void main() {
  testWidgets('batch mới khi đã đăng nhập hiện banner', (tester) async {
    final (c, _) = await pumpApp(tester, AuthStatus.signedIn);
    liveOf(c).push('Mail khẩn');
    await tester.pump();
    expect(find.text('Mail khẩn'), findsOneWidget);
    expect(find.text('Mở'), findsOneWidget);
    await tester.pumpAndSettle(const Duration(seconds: 7));
  });

  testWidgets('batch mới khi đang khoá không hiện banner', (tester) async {
    final (c, _) = await pumpApp(tester, AuthStatus.locked);
    liveOf(c).push('Mail khẩn');
    await tester.pump();
    expect(find.text('Mail khẩn'), findsNothing);
    expect(find.byType(SnackBar), findsNothing);
  });

  testWidgets('banner đang hiện biến mất khi khoá hoặc đăng xuất', (tester) async {
    for (final next in [AuthStatus.locked, AuthStatus.signedOut]) {
      final (c, auth) = await pumpApp(tester, AuthStatus.signedIn);
      liveOf(c).push('Mail khẩn');
      await tester.pump();
      expect(find.text('Mail khẩn'), findsOneWidget);
      auth.set(next);
      await tester.pumpAndSettle();
      expect(find.text('Mail khẩn'), findsNothing, reason: 'sau khi chuyển sang $next');
    }
  });
}
