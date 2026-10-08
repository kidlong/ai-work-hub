import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../core/format.dart';
import '../../data/providers.dart';
import '../../domain/models.dart';
import '../../widgets/common.dart';
import '../item/item_sheet.dart';

class TodayScreen extends ConsumerWidget {
  const TodayScreen({super.key});

  Future<void> _refresh(WidgetRef ref, BuildContext context) async {
    try {
      await ref.read(repositoryProvider).syncNow();
    } catch (e) {
      if (context.mounted) showSnack(context, ApiException.from(e).message);
    }
    refreshWorkData(ref);
    try {
      await ref.read(todayProvider.future);
    } catch (_) {
      // Lỗi đã được hiển thị bởi AsyncBody
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final today = ref.watch(todayProvider);
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: AsyncBody(
          value: today,
          onRetry: () => ref.invalidate(todayProvider),
          data: (d) => RefreshIndicator(
            onRefresh: () => _refresh(ref, context),
            child: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
              _Header(data: d),
              if (d.briefReady || DateTime.now().hour < 11) ...[const SizedBox(height: 16), const _BriefBanner()],
              const SizedBox(height: 16),
              _StatStrip(stats: d.stats),
              SectionHeader('Ưu tiên hàng đầu', icon: Icons.flag_outlined,
                  trailing: TextButton(onPressed: () => context.push('/items'), child: const Text('Tất cả'))),
              if (d.topPriorities.isEmpty)
                const EmptyState(icon: Icons.celebration_outlined, title: 'Không có việc gấp', message: 'Bạn đang kiểm soát tốt mọi thứ.')
              else
                for (final (i, it) in d.topPriorities.indexed) ...[
                  _RankedItem(rank: i + 1, item: it),
                  const SizedBox(height: 10),
                ],
              SectionHeader('Lịch thông minh', icon: Icons.insights),
              _InsightCard(ins: d.insights),
              SectionHeader('Cuộc họp tiếp theo', icon: Icons.event_outlined),
              if (d.nextMeetings.isEmpty)
                const EmptyState(icon: Icons.event_available_outlined, title: 'Không còn cuộc họp nào hôm nay')
              else
                for (final m in d.nextMeetings) ...[
                  WorkItemTile(
                    item: m,
                    onTap: () => showItemSheet(context, m),
                    trailing: TextButton.icon(
                      style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                      onPressed: () => context.push('/meeting/${m.id}'),
                      icon: const Icon(Icons.auto_awesome, size: 16),
                      label: const Text('Chuẩn bị'),
                    ),
                  ),
                  const SizedBox(height: 10),
                ],
              if (d.deadlines.isNotEmpty) ...[
                const SectionHeader('Hạn chót & SLA hôm nay', icon: Icons.hourglass_bottom),
                for (final it in d.deadlines) ...[
                  WorkItemTile(item: it, onTap: () => showItemSheet(context, it)),
                  const SizedBox(height: 10),
                ],
              ],
            ]),
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.data});
  final TodayData data;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final sync = data.user.lastSyncAt;
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(Fmt.weekdayDate(DateTime.now()),
              style: t.textTheme.labelLarge?.copyWith(color: t.colorScheme.secondary, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(data.greeting,
              style: t.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -0.5)),
          if (sync != null) ...[
            const SizedBox(height: 4),
            Text('Đồng bộ ${Fmt.ago(sync)} · kéo xuống để cập nhật',
                style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted)),
          ],
        ]),
      ),
      InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: () => context.push('/settings'),
        child: CircleAvatar(
          radius: 22,
          backgroundColor: t.colorScheme.primary,
          child: Text(data.user.initials,
              style: TextStyle(color: t.colorScheme.onPrimary, fontWeight: FontWeight.w700)),
        ),
      ),
    ]);
  }
}

class _BriefBanner extends StatelessWidget {
  const _BriefBanner();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final dark = t.brightness == Brightness.dark;
    return Material(
      color: dark ? const Color(0xFF123A37) : AppColors.tealSoft,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => context.go('/brief'),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Icon(Icons.wb_twilight, color: t.colorScheme.secondary, size: 28),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Morning Brief hôm nay', style: TextStyle(fontWeight: FontWeight.w700, color: t.colorScheme.secondary)),
                const SizedBox(height: 2),
                Text('AI đã tóm tắt lịch, việc ưu tiên và rủi ro trong ngày.', style: t.textTheme.bodySmall),
              ]),
            ),
            Icon(Icons.chevron_right, color: t.colorScheme.secondary),
          ]),
        ),
      ),
    );
  }
}

class _StatStrip extends StatelessWidget {
  const _StatStrip({required this.stats});
  final Map<String, int> stats;

  @override
  Widget build(BuildContext context) {
    final sla = stats['sla_breached'] ?? 0;
    final tiles = [
      ('Cuộc họp', '${stats['meetings_today'] ?? 0}', Fmt.duration(stats['meeting_minutes'] ?? 0), 'info'),
      ('Đến hạn', '${stats['due_today'] ?? 0}', 'hôm nay', 'info'),
      ('Quá hạn', '${stats['overdue'] ?? 0}', 'cần xử lý', (stats['overdue'] ?? 0) > 0 ? 'warning' : 'info'),
      ('SLA', sla > 0 ? '$sla' : '${stats['sla_risk'] ?? 0}', sla > 0 ? 'đã vi phạm' : 'sắp chạm', sla > 0 ? 'critical' : 'info'),
    ];
    return Row(children: [
      for (final (i, s) in tiles.indexed) ...[
        if (i > 0) const SizedBox(width: 8),
        Expanded(child: _Stat(label: s.$1, value: s.$2, sub: s.$3, severity: s.$4)),
      ],
    ]);
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value, required this.sub, required this.severity});
  final String label, value, sub, severity;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final hot = severity != 'info';
    final color = hot ? Severity.color(severity) : t.colorScheme.onSurface;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 10),
      decoration: BoxDecoration(
        color: hot ? Severity.soft(severity, t.brightness) : t.cardTheme.color,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: hot ? Colors.transparent : t.dividerTheme.color!),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: t.textTheme.labelSmall?.copyWith(color: hot ? color : AppColors.muted, fontWeight: FontWeight.w600)),
        const SizedBox(height: 4),
        Text(value, style: t.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800, color: color, height: 1)),
        const SizedBox(height: 2),
        Text(sub, maxLines: 1, overflow: TextOverflow.ellipsis,
            style: t.textTheme.labelSmall?.copyWith(color: hot ? color : AppColors.muted)),
      ]),
    );
  }
}

class _RankedItem extends StatelessWidget {
  const _RankedItem({required this.rank, required this.item});
  final int rank;
  final WorkItem item;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final sev = Severity.bucketSeverity(item.bucket);
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(
        width: 28,
        child: Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text('$rank', style: t.textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w900, color: Severity.color(sev).withValues(alpha: 0.85))),
        ),
      ),
      Expanded(child: WorkItemTile(item: item, showReasons: true, onTap: () => showItemSheet(context, item))),
    ]);
  }
}

class _InsightCard extends StatelessWidget {
  const _InsightCard({required this.ins});
  final CalendarInsight ins;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final load = ins.loadRatio.clamp(0, 1).toDouble();
    final loadColor = ins.overloaded ? AppColors.warning : t.colorScheme.secondary;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
              child: Text(
                ins.meetingCount == 0
                    ? 'Hôm nay không có cuộc họp'
                    : '${ins.meetingCount} cuộc họp · ${Fmt.duration(ins.meetingMinutes)} (${(load * 100).round()}% giờ làm)',
                style: t.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
              ),
            ),
            if (ins.overloaded) const ReasonChip('Quá tải', severity: 'warning'),
          ]),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(value: load, minHeight: 8, color: loadColor,
                backgroundColor: loadColor.withValues(alpha: 0.15)),
          ),
          for (final c in ins.conflicts.where((c) => c.end.isAfter(DateTime.now()))) ...[
            const SizedBox(height: 12),
            _InsightLine(
              icon: Icons.event_busy_outlined,
              color: AppColors.warning,
              text: 'Trùng lịch ${Fmt.hm(c.start)}–${Fmt.hm(c.end)}: “${c.aTitle}” và “${c.bTitle}”',
            ),
          ],
          for (final chain in ins.backToBack) ...[
            const SizedBox(height: 12),
            _InsightLine(
              icon: Icons.linear_scale,
              color: AppColors.warning,
              text: '${chain.length} cuộc họp liền nhau không nghỉ — nên xin 10 phút giải lao.',
            ),
          ],
          if (ins.focusSlots.isNotEmpty) ...[
            const SizedBox(height: 12),
            _InsightLine(
              icon: Icons.center_focus_strong_outlined,
              color: t.colorScheme.secondary,
              text: 'Khung giờ tập trung: ${ins.focusSlots.map((f) => '${Fmt.hm(f.start)}–${Fmt.hm(f.end)}').join(', ')}. '
                  'Gợi ý chặn lịch để xử lý việc ưu tiên số 1.',
            ),
          ] else if (ins.meetingCount > 0) ...[
            const SizedBox(height: 12),
            const _InsightLine(
              icon: Icons.do_not_disturb_on_outlined,
              color: AppColors.muted,
              text: 'Không còn khoảng trống ≥ 90 phút. Cân nhắc từ chối cuộc họp không bắt buộc.',
            ),
          ],
        ]),
      ),
    );
  }
}

class _InsightLine extends StatelessWidget {
  const _InsightLine({required this.icon, required this.color, required this.text});
  final IconData icon;
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) => Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 10),
        Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyMedium?.copyWith(height: 1.35))),
      ]);
}
