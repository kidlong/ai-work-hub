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

class BriefScreen extends ConsumerStatefulWidget {
  const BriefScreen({super.key});

  @override
  ConsumerState<BriefScreen> createState() => _BriefScreenState();
}

class _BriefScreenState extends ConsumerState<BriefScreen> {
  bool _regenerating = false;

  Future<void> _regenerate() async {
    setState(() => _regenerating = true);
    try {
      await ref.read(repositoryProvider).syncNow();
      await ref.read(repositoryProvider).brief(regenerate: true);
      ref.invalidate(briefProvider);
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    } finally {
      if (mounted) setState(() => _regenerating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final brief = ref.watch(briefProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Morning Brief'),
        actions: [
          IconButton(
            tooltip: 'Tạo lại với dữ liệu mới nhất',
            onPressed: _regenerating ? null : _regenerate,
            icon: _regenerating
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
          ),
        ],
      ),
      body: AsyncBody(
        value: brief,
        onRetry: () => ref.invalidate(briefProvider),
        data: (b) => _BriefView(brief: b),
      ),
    );
  }
}

class _BriefView extends StatelessWidget {
  const _BriefView({required this.brief});
  final DailyBrief brief;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 40), children: [
      // ----- Hero
      Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [AppColors.ink, Color(0xFF1F3A5F)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text(Fmt.weekdayDate(DateTime.parse(brief.date)),
                style: const TextStyle(color: Color(0xFFB9C7E4), fontWeight: FontWeight.w600)),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(brief.byAi ? Icons.auto_awesome : Icons.rule, size: 13, color: const Color(0xFF7EE0D3)),
                const SizedBox(width: 4),
                Text(brief.byAi ? 'AI tạo' : 'Tự động',
                    style: const TextStyle(fontSize: 11, color: Color(0xFF7EE0D3), fontWeight: FontWeight.w700)),
              ]),
            ),
          ]),
          const SizedBox(height: 10),
          Text(brief.greeting,
              style: t.textTheme.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          Text(brief.headline,
              style: t.textTheme.bodyLarge?.copyWith(color: const Color(0xFFE3E9F5), height: 1.45)),
          const SizedBox(height: 12),
          Text('Cập nhật lúc ${Fmt.hm(brief.createdAt)}',
              style: t.textTheme.labelSmall?.copyWith(color: const Color(0xFF8FA0C2))),
        ]),
      ),

      // ----- Top 3
      if (brief.topPriorities.isNotEmpty) ...[
        const SectionHeader('3 việc nên làm trước', icon: Icons.flag_outlined),
        for (final (i, p) in brief.topPriorities.indexed) ...[
          _PriorityCard(rank: i + 1, p: p),
          const SizedBox(height: 10),
        ],
      ],

      // ----- Lịch
      if (brief.schedule.isNotEmpty) ...[
        const SectionHeader('Lịch hôm nay', icon: Icons.event_outlined),
        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Column(children: [
              for (final (i, s) in brief.schedule.indexed) _ScheduleRow(slot: s, last: i == brief.schedule.length - 1),
            ]),
          ),
        ),
      ],

      // ----- Hạn chót
      if (brief.deadlines.isNotEmpty) ...[
        const SectionHeader('Hạn chót trong ngày', icon: Icons.hourglass_bottom),
        Card(
          child: Column(children: [
            for (final d in brief.deadlines)
              ListTile(
                leading: SourceBadge(d.source, dense: true),
                title: Text(d.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                trailing: Text(d.due, style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
          ]),
        ),
      ],

      // ----- Rủi ro
      if (brief.risks.isNotEmpty) ...[
        const SectionHeader('Rủi ro cần lưu ý', icon: Icons.warning_amber_rounded),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: Severity.soft('warning', t.brightness), borderRadius: BorderRadius.circular(14)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final r in brief.risks)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Icon(Icons.error_outline, size: 18, color: AppColors.warning),
                  const SizedBox(width: 10),
                  Expanded(child: Text(r, style: const TextStyle(height: 1.35))),
                ]),
              ),
          ]),
        ),
      ],

      // ----- Gợi ý
      if (brief.suggestions.isNotEmpty) ...[
        const SectionHeader('Gợi ý hành động', icon: Icons.tips_and_updates_outlined),
        _SuggestionList(items: brief.suggestions),
      ],

      if (brief.focusSlots.isNotEmpty) ...[
        const SectionHeader('Khung giờ tập trung', icon: Icons.center_focus_strong_outlined),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final f in brief.focusSlots)
            Chip(avatar: const Icon(Icons.lock_clock, size: 16), label: Text(f)),
        ]),
      ],

      const SizedBox(height: 24),
      Center(
        child: Text(brief.closing,
            textAlign: TextAlign.center,
            style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.secondary, fontStyle: FontStyle.italic)),
      ),
      if (brief.byAi) ...[
        const SizedBox(height: 12),
        Text('Nội dung do AI nội bộ tạo dựa trên dữ liệu của bạn. Hãy kiểm tra lại trước khi ra quyết định.',
            textAlign: TextAlign.center, style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted)),
      ],
    ]);
  }
}

class _PriorityCard extends ConsumerWidget {
  const _PriorityCard({required this.rank, required this.p});
  final int rank;
  final BriefPriority p;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => showItemSheetById(context, ref, p.itemId),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            CircleAvatar(
              radius: 15,
              backgroundColor: t.colorScheme.primary,
              child: Text('$rank', style: TextStyle(color: t.colorScheme.onPrimary, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SourceBadge(p.source, dense: true),
                const SizedBox(height: 6),
                Text(p.title, style: t.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600, height: 1.3)),
                const SizedBox(height: 4),
                Text(p.why, style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted, height: 1.35)),
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}

class _ScheduleRow extends StatelessWidget {
  const _ScheduleRow({required this.slot, required this.last});
  final BriefSlot slot;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final conflict = slot.note == 'Trùng lịch';
    final start = slot.time.split('-').first;
    return InkWell(
      onTap: () => context.push('/meeting/${slot.itemId}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            width: 48,
            child: Text(start, style: t.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
          ),
          Column(children: [
            Container(
              width: 10,
              height: 10,
              margin: const EdgeInsets.only(top: 4),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: conflict ? AppColors.warning : t.colorScheme.secondary,
              ),
            ),
            if (!last) Container(width: 2, height: 38, color: t.dividerTheme.color),
          ]),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(slot.title, style: t.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text([slot.time, if (slot.location.isNotEmpty) slot.location].join(' · '),
                  style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted)),
            ]),
          ),
          if (slot.note.isNotEmpty) ReasonChip(slot.note, severity: conflict ? 'warning' : 'info'),
        ]),
      ),
    );
  }
}

class _SuggestionList extends StatefulWidget {
  const _SuggestionList({required this.items});
  final List<String> items;

  @override
  State<_SuggestionList> createState() => _SuggestionListState();
}

class _SuggestionListState extends State<_SuggestionList> {
  final _done = <int>{};

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(children: [
        for (final (i, s) in widget.items.indexed)
          CheckboxListTile(
            value: _done.contains(i),
            onChanged: (v) => setState(() => v == true ? _done.add(i) : _done.remove(i)),
            controlAffinity: ListTileControlAffinity.leading,
            title: Text(
              s,
              style: TextStyle(
                decoration: _done.contains(i) ? TextDecoration.lineThrough : null,
                color: _done.contains(i) ? AppColors.muted : null,
              ),
            ),
          ),
      ]),
    );
  }
}
