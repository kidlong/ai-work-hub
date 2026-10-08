import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/notifications/local_notifications.dart';
import '../../data/providers.dart';

class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key, required this.shell});
  final StatefulNavigationShell shell;

  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  @override
  void initState() {
    super.initState();
    final ln = LocalNotifications.instance;
    ln.onTap = _handlePayload;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(notificationSyncProvider).resync().ignore();
      final p = ln.launchPayload;
      if (p != null) {
        ln.launchPayload = null;
        _handlePayload(p);
      }
    });
  }

  void _handlePayload(String payload) {
    if (!mounted) return;
    if (payload == 'brief') {
      context.go('/brief');
    } else if (payload.startsWith('item:')) {
      context.go('/alerts');
    } else {
      context.go('/alerts');
    }
  }

  @override
  Widget build(BuildContext context) {
    final pending = ref.watch(todayProvider).value?.pendingAlerts ?? 0;
    return Scaffold(
      body: widget.shell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: widget.shell.currentIndex,
        onDestinationSelected: (i) => widget.shell.goBranch(i, initialLocation: i == widget.shell.currentIndex),
        destinations: [
          const NavigationDestination(icon: Icon(Icons.today_outlined), selectedIcon: Icon(Icons.today), label: 'Hôm nay'),
          NavigationDestination(
            icon: Badge(isLabelVisible: pending > 0, label: Text('$pending'), child: const Icon(Icons.notifications_outlined)),
            selectedIcon: Badge(isLabelVisible: pending > 0, label: Text('$pending'), child: const Icon(Icons.notifications)),
            label: 'Nhắc việc',
          ),
          const NavigationDestination(icon: Icon(Icons.wb_twilight_outlined), selectedIcon: Icon(Icons.wb_twilight), label: 'Brief'),
          const NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), selectedIcon: Icon(Icons.auto_awesome), label: 'Hỏi AI'),
        ],
      ),
    );
  }
}
