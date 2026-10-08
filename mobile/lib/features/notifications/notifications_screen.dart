import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../core/format.dart';
import '../../data/providers.dart';
import '../../domain/models.dart';
import '../../widgets/common.dart';
import '../item/item_sheet.dart';

class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  String _scope = 'active';

  Future<void> _ackAll() async {
    try {
      await ref.read(repositoryProvider).ackAll();
      refreshWorkData(ref);
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final alerts = ref.watch(alertsProvider(_scope));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Nhắc việc thông minh'),
        actions: [
          if (_scope == 'active')
            IconButton(tooltip: 'Đánh dấu đã xem tất cả', onPressed: _ackAll, icon: const Icon(Icons.done_all)),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(56),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'active', label: Text('Cần xử lý'), icon: Icon(Icons.notifications_active_outlined)),
                ButtonSegment(value: 'upcoming', label: Text('Sắp tới'), icon: Icon(Icons.update)),
              ],
              selected: {_scope},
              showSelectedIcon: false,
              onSelectionChanged: (s) => setState(() => _scope = s.first),
              style: const ButtonStyle(visualDensity: VisualDensity.compact),
            ),
          ),
        ),
      ),
      body: AsyncBody(
        value: alerts,
        onRetry: () => ref.invalidate(alertsProvider(_scope)),
        data: (list) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(alertsProvider(_scope));
            try {
              await ref.read(alertsProvider(_scope).future);
            } catch (_) {}
          },
          child: list.isEmpty
              ? ListView(children: [
                  EmptyState(
                    icon: _scope == 'active' ? Icons.notifications_off_outlined : Icons.event_available_outlined,
                    title: _scope == 'active' ? 'Không còn nhắc nào cần xử lý' : 'Chưa có nhắc nào sắp tới',
                    message: 'AI Work Hub theo dõi lịch, email, Jira, Confluence, SDP và Teams cho bạn.',
                  ),
                ])
              : ListView.separated(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                  itemCount: list.length + 1,
                  separatorBuilder: (_, _) => const SizedBox(height: 10),
                  itemBuilder: (ctx, i) => i == 0
                      ? Text(
                          _scope == 'active'
                              ? 'Vuốt sang phải để hoãn 1 giờ, sang trái để đánh dấu đã xem.'
                              : 'Các nhắc này cũng được lên lịch trên máy, vẫn báo khi mất kết nối.',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: AppColors.muted),
                        )
                      : _AlertTile(alert: list[i - 1], swipeable: _scope == 'active'),
                ),
        ),
      ),
    );
  }
}

class _AlertTile extends ConsumerWidget {
  const _AlertTile({required this.alert, required this.swipeable});
  final AlertModel alert;
  final bool swipeable;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final color = Severity.color(alert.severity);
    final card = AccentCard(
      color: color,
      onTap: alert.workItemId == null ? null : () => showItemSheetById(context, ref, alert.workItemId!),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(color: Severity.soft(alert.severity, t.brightness), borderRadius: BorderRadius.circular(10)),
          child: Icon(alertIcon(alert.kind), size: 20, color: color),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(alert.title, style: t.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600, height: 1.3)),
            if (alert.body.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(alert.body, style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted, height: 1.35)),
            ],
            const SizedBox(height: 6),
            Text(
              swipeable ? Fmt.ago(alert.fireAt) : 'Sẽ nhắc lúc ${Fmt.smartTime(alert.fireAt)}',
              style: t.textTheme.labelSmall?.copyWith(color: AppColors.muted),
            ),
          ]),
        ),
      ]),
    );
    if (!swipeable) return card;

    final repo = ref.read(repositoryProvider);
    return Dismissible(
      key: ValueKey('alert-${alert.id}'),
      background: _swipeBg(context, Icons.snooze, 'Hoãn 1 giờ', AppColors.info, Alignment.centerLeft),
      secondaryBackground: _swipeBg(context, Icons.done, 'Đã xem', AppColors.ok, Alignment.centerRight),
      confirmDismiss: (dir) async {
        try {
          if (dir == DismissDirection.startToEnd) {
            await repo.snoozeAlert(alert.id, const Duration(hours: 1));
          } else {
            await repo.ackAlert(alert.id);
          }
          return true;
        } catch (e) {
          if (context.mounted) showSnack(context, ApiException.from(e).message);
          return false;
        }
      },
      onDismissed: (_) => refreshWorkData(ref),
      child: card,
    );
  }

  Widget _swipeBg(BuildContext context, IconData icon, String label, Color color, Alignment align) => Container(
        alignment: align,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(16)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, color: color),
          const SizedBox(width: 8),
          Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w700)),
        ]),
      );
}
