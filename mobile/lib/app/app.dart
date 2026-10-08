import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/providers.dart';
import 'router.dart';
import 'theme.dart';

class AiWorkHubApp extends ConsumerStatefulWidget {
  const AiWorkHubApp({super.key});

  @override
  ConsumerState<AiWorkHubApp> createState() => _AiWorkHubAppState();
}

class _AiWorkHubAppState extends ConsumerState<AiWorkHubApp> with WidgetsBindingObserver {
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
    if (state == AppLifecycleState.paused) {
      auth.onPaused();
    } else if (state == AppLifecycleState.resumed) {
      auth.onResumed();
      if (ref.read(authProvider).status == AuthStatus.signedIn) {
        ref.invalidate(todayProvider);
        ref.read(notificationSyncProvider).resync().ignore();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'AI Work Hub',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      routerConfig: ref.watch(routerProvider),
      locale: const Locale('vi'),
      supportedLocales: const [Locale('vi'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
    );
  }
}
