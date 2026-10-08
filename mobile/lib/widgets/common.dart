import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../app/theme.dart';
import '../core/api_client.dart';
import '../core/format.dart';
import '../domain/models.dart';

class SourceBadge extends StatelessWidget {
  const SourceBadge(this.source, {super.key, this.dense = false});
  final String source;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final m = SourceMeta.of(source);
    return Container(
      padding: EdgeInsets.symmetric(horizontal: dense ? 6 : 8, vertical: dense ? 2 : 3),
      decoration: BoxDecoration(color: m.color.withValues(alpha: 0.10), borderRadius: BorderRadius.circular(6)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(m.icon, size: dense ? 12 : 14, color: m.color),
        const SizedBox(width: 4),
        Text(m.label, style: TextStyle(fontSize: dense ? 11 : 12, fontWeight: FontWeight.w600, color: m.color)),
      ]),
    );
  }
}

class AiBadge extends StatelessWidget {
  const AiBadge({super.key, required this.byAi});
  final bool byAi;

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme.secondary;
    return Tooltip(
      message: byAi ? 'Nội dung do AI nội bộ tạo, hãy kiểm tra lại trước khi dùng' : 'Tổng hợp tự động theo quy tắc',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(border: Border.all(color: c.withValues(alpha: 0.5)), borderRadius: BorderRadius.circular(20)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(byAi ? Icons.auto_awesome : Icons.rule, size: 13, color: c),
          const SizedBox(width: 4),
          Text(byAi ? 'AI tạo' : 'Tự động', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: c)),
        ]),
      ),
    );
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.trailing, this.icon});
  final String title;
  final Widget? trailing;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 20, 4, 10),
      child: Row(children: [
        if (icon != null) ...[Icon(icon, size: 18, color: t.colorScheme.secondary), const SizedBox(width: 8)],
        Expanded(
          child: Text(title, style: t.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.2)),
        ),
        ?trailing,
      ]),
    );
  }
}

/// Card có dải màu bên trái thể hiện mức độ.
class AccentCard extends StatelessWidget {
  const AccentCard({super.key, required this.color, required this.child, this.onTap, this.padding = const EdgeInsets.all(14)});
  final Color color;
  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: IntrinsicHeight(
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Container(width: 4, color: color),
            Expanded(child: Padding(padding: padding, child: child)),
          ]),
        ),
      ),
    );
  }
}

class WorkItemTile extends StatelessWidget {
  const WorkItemTile({super.key, required this.item, this.onTap, this.showReasons = false, this.trailing});
  final WorkItem item;
  final VoidCallback? onTap;
  final bool showReasons;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final now = DateTime.now();
    final sev = Severity.bucketSeverity(item.bucket);
    final overdue = item.isOverdue(now);
    final time = item.keyTime;
    return AccentCard(
      color: item.bucket == 'low' || item.bucket == 'normal' ? t.dividerTheme.color! : Severity.color(sev),
      onTap: onTap,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          SourceBadge(item.source, dense: true),
          const SizedBox(width: 8),
          if (time != null)
            Expanded(
              child: Text(
                item.isMeeting
                    ? '${Fmt.smartTime(item.startAt)}–${Fmt.hm(item.endAt)}'
                    : '${Fmt.smartTime(time)} · ${Fmt.relative(time)}',
                overflow: TextOverflow.ellipsis,
                style: t.textTheme.labelMedium?.copyWith(
                  color: overdue ? AppColors.critical : AppColors.muted,
                  fontWeight: overdue ? FontWeight.w700 : FontWeight.w500,
                ),
              ),
            )
          else
            const Spacer(),
          ?trailing,
        ]),
        const SizedBox(height: 8),
        Text(item.title, maxLines: 2, overflow: TextOverflow.ellipsis,
            style: t.textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600, height: 1.3)),
        if (showReasons && item.scoreReasons.isNotEmpty) ...[
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final r in item.scoreReasons.take(3)) ReasonChip(r, severity: sev),
          ]),
        ] else if (item.location.isNotEmpty && item.isMeeting) ...[
          const SizedBox(height: 4),
          Row(children: [
            const Icon(Icons.place_outlined, size: 14, color: AppColors.muted),
            const SizedBox(width: 4),
            Expanded(child: Text(item.location, style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted))),
          ]),
        ],
      ]),
    );
  }
}

class ReasonChip extends StatelessWidget {
  const ReasonChip(this.text, {super.key, this.severity = 'info'});
  final String text;
  final String severity;

  @override
  Widget build(BuildContext context) {
    final b = Theme.of(context).brightness;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: Severity.soft(severity, b), borderRadius: BorderRadius.circular(6)),
      child: Text(text, style: TextStyle(fontSize: 12, color: Severity.color(severity), fontWeight: FontWeight.w600)),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.message});
  final IconData icon;
  final String title;
  final String? message;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 32),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 44, color: t.colorScheme.secondary.withValues(alpha: 0.6)),
        const SizedBox(height: 12),
        Text(title, textAlign: TextAlign.center, style: t.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
        if (message != null) ...[
          const SizedBox(height: 6),
          Text(message!, textAlign: TextAlign.center, style: t.textTheme.bodyMedium?.copyWith(color: AppColors.muted)),
        ],
      ]),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, required this.onRetry});
  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.cloud_off_outlined, size: 44, color: AppColors.muted),
          const SizedBox(height: 12),
          Text(ApiException.from(error).message, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          OutlinedButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Thử lại')),
        ]),
      ),
    );
  }
}

/// Hiển thị AsyncValue với trạng thái tải / lỗi thống nhất.
class AsyncBody<T> extends StatelessWidget {
  const AsyncBody({super.key, required this.value, required this.data, required this.onRetry});
  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return switch (value) {
      AsyncValue(:final T value, hasValue: true) => data(value),
      AsyncValue(:final Object error, hasError: true) => ErrorView(error: error, onRetry: onRetry),
      _ => const Center(child: CircularProgressIndicator()),
    };
  }
}

void showSnack(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message), behavior: SnackBarBehavior.floating));
}
