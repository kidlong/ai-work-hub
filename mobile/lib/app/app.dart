import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/live_events.dart';
import '../data/providers.dart';
import '../features/item/item_sheet.dart';
import 'router.dart';
import 'theme.dart';

class AiWorkHubApp extends ConsumerStatefulWidget {
  const AiWorkHubApp({super.key});

  @override
  ConsumerState<AiWorkHubApp> createState() => _AiWorkHubAppState();
}

class _AiWorkHubAppState extends ConsumerState<AiWorkHubApp> with WidgetsBindingObserver {
  final _messengerKey = GlobalKey<ScaffoldMessengerState>();
  bool _foreground = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final auth = ref.read(authProvider.notifier);
    final live = ref.read(liveEventsProvider.notifier);
    if (state == AppLifecycleState.paused) {
      _foreground = false;
      auth.onPaused();
      live.stop();
    } else if (state == AppLifecycleState.resumed) {
      _foreground = true;
      auth.onResumed();
      if (ref.read(authProvider).status == AuthStatus.signedIn) {
        ref.invalidate(todayProvider);
        ref.read(notificationSyncProvider).resync().ignore();
        live.start();
      }
    }
  }

  void _onAuth(AuthStatus status) {
    final live = ref.read(liveEventsProvider.notifier);
    switch (status) {
      case AuthStatus.signedIn:
        if (_foreground) live.start();
      case AuthStatus.signedOut:
        live.reset();
      case AuthStatus.unknown || AuthStatus.locked:
        live.stop();
    }
    // Banner (và nút "Mở") không được còn trên màn hình khoá / đăng nhập.
    if (status != AuthStatus.signedIn) _messengerKey.currentState?.hideCurrentSnackBar();
  }

  void _onLive(LiveFeedState? prev, LiveFeedState next) {
    if (next.batch.isEmpty || next.seq == (prev?.seq ?? 0)) return;
    // Một poll còn bay có thể về sau khi app đã khoá / đăng xuất: không hiện banner, không làm mới dữ liệu.
    if (ref.read(authProvider).status != AuthStatus.signedIn) return;
    refreshWorkData(ref);
    final messenger = _messengerKey.currentState;
    if (messenger == null) return;
    final last = next.batch.last;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 6),
        backgroundColor: Severity.color(last.severity),
        content: Text(liveBannerText(next.batch), style: const TextStyle(color: Colors.white)),
        action: last.workItemId == null
            ? null
            : SnackBarAction(label: 'Mở', textColor: Colors.white, onPressed: () => _openItem(last.workItemId!)),
      ));
  }

  void _openItem(int id) {
    final ctx = ref.read(routerProvider).routerDelegate.navigatorKey.currentContext;
    if (ctx != null) showItemSheetById(ctx, ref, id);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthState>(authProvider, (_, next) => _onAuth(next.status));
    ref.listen<LiveFeedState>(liveEventsProvider, _onLive);
    return MaterialApp.router(
      title: 'AI Work Hub',
      debugShowCheckedModeBanner: false,
      scaffoldMessengerKey: _messengerKey,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      routerConfig: ref.watch(routerProvider),
      locale: const Locale('vi'),
      supportedLocales: const [Locale('vi'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
    );
  }
}
