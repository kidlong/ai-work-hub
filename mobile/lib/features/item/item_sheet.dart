import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../core/format.dart';
import '../../data/providers.dart';
import '../../domain/models.dart';
import '../../widgets/common.dart';

Future<void> showItemSheet(BuildContext context, WorkItem item) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    builder: (_) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.62,
      maxChildSize: 0.92,
      builder: (ctx, controller) => ItemSheet(item: item, controller: controller),
    ),
  );
}

/// Mở sheet theo id (dùng khi chạm vào nhắc việc / thông báo).
Future<void> showItemSheetById(BuildContext context, WidgetRef ref, int id) async {
  try {
    final item = await ref.read(repositoryProvider).workItem(id);
    if (context.mounted) await showItemSheet(context, item);
  } catch (e) {
    if (context.mounted) showSnack(context, ApiException.from(e).message);
  }
}

Future<void> openExternal(BuildContext context, String url) async {
  final uri = Uri.tryParse(url);
  if (uri == null || !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
    if (context.mounted) showSnack(context, 'Không mở được liên kết. Kiểm tra VPN nội bộ.');
  }
}

class ItemSheet extends ConsumerStatefulWidget {
  const ItemSheet({super.key, required this.item, required this.controller});
  final WorkItem item;
  final ScrollController controller;

  @override
  ConsumerState<ItemSheet> createState() => _ItemSheetState();
}

class _ItemSheetState extends ConsumerState<ItemSheet> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action, String done) async {
    setState(() => _busy = true);
    try {
      await action();
      refreshWorkData(ref);
      if (mounted) {
        Navigator.of(context).pop();
        showSnack(context, done);
      }
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _snooze() async {
    final now = DateTime.now();
    final tomorrow8 = DateTime(now.year, now.month, now.day + 1, 8);
    final choice = await showModalBottomSheet<Duration>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const ListTile(title: Text('Hoãn nhắc đến…', style: TextStyle(fontWeight: FontWeight.w700))),
          ListTile(leading: const Icon(Icons.timer_outlined), title: const Text('1 giờ nữa'),
              onTap: () => Navigator.pop(ctx, const Duration(hours: 1))),
          ListTile(leading: const Icon(Icons.timelapse), title: const Text('3 giờ nữa'),
              onTap: () => Navigator.pop(ctx, const Duration(hours: 3))),
          ListTile(leading: const Icon(Icons.wb_twilight), title: const Text('8:00 sáng mai'),
              onTap: () => Navigator.pop(ctx, tomorrow8.difference(now))),
        ]),
      ),
    );
    if (choice != null) {
      await _run(() => ref.read(repositoryProvider).snoozeItem(widget.item.id, choice), 'Đã hoãn nhắc');
    }
  }

  @override
  Widget build(BuildContext context) {
    final it = widget.item;
    final t = Theme.of(context);
    final sev = Severity.bucketSeverity(it.bucket);
    final repo = ref.read(repositoryProvider);

    return ListView(controller: widget.controller, padding: const EdgeInsets.fromLTRB(20, 0, 20, 24), children: [
      Row(children: [
        SourceBadge(it.source),
        const SizedBox(width: 8),
        if (it.status.isNotEmpty) Chip(label: Text(it.status), visualDensity: VisualDensity.compact),
        const Spacer(),
        if (it.priorityRaw.isNotEmpty)
          Text('Ưu tiên: ${it.priorityRaw}', style: t.textTheme.labelMedium?.copyWith(color: AppColors.muted)),
      ]),
      const SizedBox(height: 12),
      Text(it.title, style: t.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700, height: 1.3)),
      const SizedBox(height: 12),
      _InfoRow(icon: Icons.schedule, text: _timeLine(it)),
      if (it.requester.isNotEmpty)
        _InfoRow(icon: Icons.person_outline, text: '${it.isMeeting ? 'Người tổ chức' : 'Người yêu cầu'}: ${it.requester}'),
      if (it.location.isNotEmpty) _InfoRow(icon: Icons.place_outlined, text: it.location),
      if (it.participants.isNotEmpty) _InfoRow(icon: Icons.groups_outlined, text: '${it.participants.length} người tham dự'),

      if (it.scoreReasons.isNotEmpty) ...[
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: Severity.soft(sev, t.brightness), borderRadius: BorderRadius.circular(12)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(Icons.insights, size: 18, color: Severity.color(sev)),
              const SizedBox(width: 8),
              Text('Vì sao mục này được ưu tiên', style: TextStyle(fontWeight: FontWeight.w700, color: Severity.color(sev))),
              const Spacer(),
              Text('${it.score.round()}/100', style: TextStyle(fontWeight: FontWeight.w800, color: Severity.color(sev))),
            ]),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: it.score / 100, minHeight: 6,
                color: Severity.color(sev), backgroundColor: Severity.color(sev).withValues(alpha: 0.15),
              ),
            ),
            const SizedBox(height: 10),
            for (final r in it.scoreReasons)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('•  ', style: TextStyle(color: Severity.color(sev))),
                  Expanded(child: Text(r)),
                ]),
              ),
          ]),
        ),
      ],
      if (it.preview.isNotEmpty) ...[
        const SizedBox(height: 16),
        Text('Nội dung', style: t.textTheme.labelLarge?.copyWith(color: AppColors.muted)),
        const SizedBox(height: 6),
        Text(it.preview, style: t.textTheme.bodyMedium?.copyWith(height: 1.45)),
      ],
      const SizedBox(height: 24),
      if (it.isMeeting) ...[
        FilledButton.icon(
          onPressed: () {
            Navigator.of(context).pop();
            context.push('/meeting/${it.id}');
          },
          icon: const Icon(Icons.auto_awesome),
          label: const Text('Chuẩn bị cho cuộc họp'),
        ),
        const SizedBox(height: 10),
      ],
      if (it.url.isNotEmpty)
        OutlinedButton.icon(
          onPressed: () => openExternal(context, it.url),
          icon: const Icon(Icons.open_in_new),
          label: Text(SourceMeta.openLabel(it.source)),
        ),
      const SizedBox(height: 10),
      Row(children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: _busy ? null : _snooze,
            icon: const Icon(Icons.snooze),
            label: const Text('Hoãn nhắc'),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: _busy
                ? null
                : () => it.doneLocal
                    ? _run(() => repo.markUndone(it.id), 'Đã bỏ đánh dấu')
                    : _run(() => repo.markDone(it.id), 'Đã ẩn khỏi danh sách của bạn'),
            icon: Icon(it.doneLocal ? Icons.undo : Icons.check_circle_outline),
            label: Text(it.doneLocal ? 'Bỏ đánh dấu' : 'Đã xong'),
          ),
        ),
      ]),
      const SizedBox(height: 8),
      Text(
        '“Đã xong” chỉ ẩn mục trên AI Work Hub, không thay đổi trạng thái ở hệ thống gốc.',
        textAlign: TextAlign.center,
        style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted),
      ),
    ]);
  }

  String _timeLine(WorkItem it) {
    if (it.isMeeting) return '${Fmt.smartTime(it.startAt)} – ${Fmt.hm(it.endAt)}  (${Fmt.relative(it.startAt)})';
    final parts = <String>[];
    if (it.dueAt != null) parts.add('Hạn: ${Fmt.smartTime(it.dueAt)} (${Fmt.relative(it.dueAt)})');
    if (it.slaDueAt != null) parts.add('SLA: ${Fmt.smartTime(it.slaDueAt)} (${Fmt.relative(it.slaDueAt)})');
    if (parts.isEmpty && it.startAt != null) parts.add('Nhận lúc ${Fmt.smartTime(it.startAt)}');
    return parts.isEmpty ? 'Không có hạn' : parts.join('\n');
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 18, color: AppColors.muted),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyMedium)),
        ]),
      );
}
