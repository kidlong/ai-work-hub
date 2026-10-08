import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../data/providers.dart';
import '../../domain/models.dart';
import '../../widgets/common.dart';
import '../item/item_sheet.dart';

class MeetingPrepScreen extends ConsumerWidget {
  const MeetingPrepScreen({super.key, required this.itemId});
  final int itemId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final prep = ref.watch(meetingPrepProvider(itemId));
    return Scaffold(
      appBar: AppBar(title: const Text('Chuẩn bị họp')),
      body: AsyncBody(
        value: prep,
        onRetry: () => ref.invalidate(meetingPrepProvider(itemId)),
        data: (p) => _PrepView(p: p),
      ),
    );
  }
}

class _PrepView extends ConsumerWidget {
  const _PrepView({required this.p});
  final MeetingPrep p;

  String _countdown() {
    final m = p.minutesToStart;
    if (p.ended) return 'Đã kết thúc';
    if (m == null) return '';
    if (m < 0) return 'Đang diễn ra';
    if (m < 60) return 'Bắt đầu sau $m phút';
    if (m < 60 * 24) return 'Bắt đầu sau ${m ~/ 60} giờ ${m % 60} phút';
    return 'Bắt đầu sau ${m ~/ (60 * 24)} ngày';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final soon = !p.ended && (p.minutesToStart ?? 999) <= 30;
    return ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 40), children: [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              if (_countdown().isNotEmpty) ReasonChip(_countdown(), severity: soon ? 'warning' : 'info'),
              const Spacer(),
              AiBadge(byAi: p.generatedBy == 'llm'),
            ]),
            const SizedBox(height: 12),
            Text(p.title, style: t.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800, height: 1.3)),
            const SizedBox(height: 12),
            _Line(Icons.schedule, '${p.start ?? ''}${p.end != null ? ' – ${p.end}' : ''}'),
            if (p.location.isNotEmpty) _Line(Icons.place_outlined, p.location),
            _Line(Icons.person_outline, p.isOrganizer ? 'Bạn là người chủ trì' : 'Tổ chức: ${p.organizer}'),
            if (p.attendees.isNotEmpty) _Line(Icons.groups_outlined, '${p.attendees.length} người tham dự'),
            if (p.url.isNotEmpty) ...[
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: () => openExternal(context, p.url),
                icon: const Icon(Icons.open_in_new, size: 18),
                label: const Text('Mở thư mời'),
              ),
            ],
          ]),
        ),
      ),
      const SectionHeader('Mục đích cuộc họp', icon: Icons.track_changes),
      Text(p.purpose, style: t.textTheme.bodyLarge?.copyWith(height: 1.45)),
      const SectionHeader('Nên chuẩn bị', icon: Icons.checklist),
      Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Column(children: [
            for (final (i, tp) in p.talkingPoints.indexed)
              ListTile(
                leading: CircleAvatar(
                  radius: 13,
                  backgroundColor: t.colorScheme.secondary.withValues(alpha: 0.12),
                  child: Text('${i + 1}', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: t.colorScheme.secondary)),
                ),
                title: Text(tp, style: const TextStyle(height: 1.35)),
              ),
          ]),
        ),
      ),
      if (p.questions.isNotEmpty) ...[
        const SectionHeader('Câu hỏi nên đặt ra', icon: Icons.help_outline),
        for (final q in p.questions)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(Icons.chat_bubble_outline, size: 18, color: t.colorScheme.secondary),
              const SizedBox(width: 10),
              Expanded(child: Text(q, style: const TextStyle(height: 1.35))),
            ]),
          ),
      ],
      const SectionHeader('Tài liệu & việc liên quan', icon: Icons.link),
      if (p.related.isEmpty)
        const EmptyState(icon: Icons.search_off, title: 'Chưa tìm thấy mục liên quan',
            message: 'Không có ticket, tài liệu hay email nào khớp với cuộc họp này.')
      else
        for (final r in p.related) ...[
          Card(
            child: ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              onTap: () => showItemSheetById(context, ref, r.itemId),
              title: Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(children: [
                  SourceBadge(r.source, dense: true),
                  if (r.status.isNotEmpty) ...[
                    const SizedBox(width: 8),
                    Text(r.status, style: t.textTheme.labelSmall?.copyWith(color: AppColors.muted)),
                  ],
                ]),
              ),
              subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(r.title, style: t.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600, color: t.colorScheme.onSurface)),
                const SizedBox(height: 2),
                Text(r.reason, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.secondary)),
              ]),
              trailing: r.url.isEmpty
                  ? null
                  : IconButton(icon: const Icon(Icons.open_in_new, size: 20), onPressed: () => openExternal(context, r.url)),
            ),
          ),
          const SizedBox(height: 8),
        ],
    ]);
  }
}

class _Line extends StatelessWidget {
  const _Line(this.icon, this.text);
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(children: [
          Icon(icon, size: 17, color: AppColors.muted),
          const SizedBox(width: 10),
          Expanded(child: Text(text)),
        ]),
      );
}
