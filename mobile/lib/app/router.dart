import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../data/providers.dart';
import '../features/assistant/assistant_screen.dart';
import '../features/brief/brief_screen.dart';
import '../features/items/all_items_screen.dart';
import '../features/login/login_screen.dart';
import '../features/meeting_prep/meeting_prep_screen.dart';
import '../features/notifications/notifications_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/shell/home_shell.dart';
import '../features/today/today_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final auth = ValueNotifier<AuthStatus>(ref.read(authProvider).status);
  ref.listen(authProvider, (_, next) => auth.value = next.status);
  ref.onDispose(auth.dispose);

  return GoRouter(
    initialLocation: '/today',
    refreshListenable: auth,
    redirect: (context, state) {
      final loc = state.matchedLocation;
      switch (auth.value) {
        case AuthStatus.unknown:
          return loc == '/splash' ? null : '/splash';
        case AuthStatus.signedOut:
          return loc == '/login' ? null : '/login';
        case AuthStatus.locked:
          return loc == '/lock' ? null : '/lock';
        case AuthStatus.signedIn:
          return (loc == '/login' || loc == '/lock' || loc == '/splash') ? '/today' : null;
      }
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, _) => const Scaffold(body: Center(child: CircularProgressIndicator()))),
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/lock', builder: (_, _) => const LockScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [GoRoute(path: '/today', builder: (_, _) => const TodayScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/alerts', builder: (_, _) => const NotificationsScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/brief', builder: (_, _) => const BriefScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/assistant', builder: (_, _) => const AssistantScreen())]),
        ],
      ),
      GoRoute(path: '/items', builder: (_, _) => const AllItemsScreen()),
      GoRoute(path: '/settings', builder: (_, _) => const SettingsScreen()),
      GoRoute(
        path: '/meeting/:id',
        builder: (_, state) => MeetingPrepScreen(itemId: int.parse(state.pathParameters['id']!)),
      ),
    ],
  );
});
