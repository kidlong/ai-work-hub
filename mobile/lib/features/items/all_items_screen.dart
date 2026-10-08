import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/format.dart';
import '../../data/providers.dart';
import '../../domain/models.dart';
import '../../widgets/common.dart';
import '../item/item_sheet.dart';

final _filterProvider = NotifierProvider.autoDispose<_Filter, String?>(_Filter.new);

class _Filter extends Notifier<String?> {
  @override
  String? build() => null;
  void set(String? v) => state = v;
}

final _itemsProvider = FutureProvider.autoDispose<List<WorkItem>>((ref) {
  final source = ref.watch(_filterProvider);
  return ref.watch(repositoryProvider).workItems(source: source);
});

/// Toàn bộ việc, sắp xếp theo điểm ưu tiên (Priority Inbox).
class AllItemsScreen extends ConsumerWidget {
  const AllItemsScreen({super.key});

  static const _sources = ['exchange_mail', 'exchange_calendar', 'jira', 'sdp', 'confluence', 'teams'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(_filterProvider);
    final items = ref.watch(_itemsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Hộp việc ưu tiên')),
      body: Column(children: [
        SizedBox(
          height: 52,
          child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 12), children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: ChoiceChip(label: const Text('Tất cả'), selected: filter == null,
                  onSelected: (_) => ref.read(_filterProvider.notifier).set(null)),
            ),
            for (final s in _sources)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: ChoiceChip(
                  avatar: Icon(SourceMeta.of(s).icon, size: 16),
                  label: Text(SourceMeta.of(s).label),
                  selected: filter == s,
                  onSelected: (_) => ref.read(_filterProvider.notifier).set(s),
                ),
              ),
          ]),
        ),
        Expanded(
          child: AsyncBody(
            value: items,
            onRetry: () => ref.invalidate(_itemsProvider),
            data: (list) => list.isEmpty
                ? const EmptyState(icon: Icons.inbox_outlined, title: 'Không có mục nào')
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
                    itemCount: list.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 10),
                    itemBuilder: (ctx, i) => WorkItemTile(
                      item: list[i],
                      showReasons: list[i].bucket == 'critical' || list[i].bucket == 'high',
                      onTap: () async {
                        await showItemSheet(context, list[i]);
                        ref.invalidate(_itemsProvider);
                      },
                    ),
                  ),
          ),
        ),
      ]),
    );
  }
}
