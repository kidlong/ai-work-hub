import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../data/providers.dart';
import '../../domain/models.dart';
import '../../widgets/common.dart';
import '../item/item_sheet.dart';

class ChatTurn {
  ChatTurn.user(this.text)
      : fromUser = true,
        result = null,
        error = false;
  ChatTurn.ai(AskResult r)
      : fromUser = false,
        // Câu trả lời tự động đã liệt kê mục; app hiện mục dạng thẻ nên chỉ giữ câu mở đầu.
        text = (r.generatedBy == 'fallback' && r.items.isNotEmpty ? r.answer.split('\n').first : r.answer)
            .replaceAll(RegExp(r'\s*\[#\d+\]'), ''),
        result = r,
        error = false;
  ChatTurn.error(this.text)
      : fromUser = false,
        result = null,
        error = true;

  final bool fromUser;
  final String text;
  final AskResult? result;
  final bool error;
}

class ChatController extends Notifier<List<ChatTurn>> {
  @override
  List<ChatTurn> build() => [];

  bool _busy = false;
  bool get busy => _busy;

  Future<void> ask(String q) async {
    if (_busy || q.trim().length < 2) return;
    _busy = true;
    state = [...state, ChatTurn.user(q.trim())];
    try {
      final r = await ref.read(repositoryProvider).ask(q.trim());
      state = [...state, ChatTurn.ai(r)];
    } catch (e) {
      state = [...state, ChatTurn.error(ApiException.from(e).message)];
    } finally {
      _busy = false;
    }
  }

  void clear() => state = [];
}

final chatProvider = NotifierProvider<ChatController, List<ChatTurn>>(ChatController.new);

const _suggestions = [
  'Hôm nay tôi nên làm gì trước?',
  'Ticket SDP nào sắp vi phạm SLA?',
  'Chiều nay tôi có họp gì?',
  'Việc nào đang quá hạn?',
  'Email nào từ quản lý chưa đọc?',
  'Jira của tôi tuần này',
];

class AssistantScreen extends ConsumerStatefulWidget {
  const AssistantScreen({super.key});

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send([String? text]) async {
    final q = text ?? _input.text;
    if (q.trim().isEmpty) return;
    _input.clear();
    FocusScope.of(context).unfocus();
    final f = ref.read(chatProvider.notifier).ask(q);
    setState(() {});
    await f;
    if (mounted) setState(() {});
    await Future<void>.delayed(const Duration(milliseconds: 50));
    if (_scroll.hasClients) {
      _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
    }
  }

  @override
  Widget build(BuildContext context) {
    final turns = ref.watch(chatProvider);
    final busy = ref.read(chatProvider.notifier).busy;
    final t = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Hỏi AI'),
        actions: [
          if (turns.isNotEmpty)
            IconButton(tooltip: 'Cuộc trò chuyện mới', onPressed: () => ref.read(chatProvider.notifier).clear(),
                icon: const Icon(Icons.add_comment_outlined)),
        ],
      ),
      body: Column(children: [
        Expanded(
          child: turns.isEmpty
              ? ListView(padding: const EdgeInsets.all(20), children: [
                  const SizedBox(height: 12),
                  Icon(Icons.auto_awesome, size: 40, color: t.colorScheme.secondary),
                  const SizedBox(height: 12),
                  Text('Hỏi về công việc của bạn', textAlign: TextAlign.center,
                      style: t.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 6),
                  Text(
                    'AI chỉ đọc dữ liệu của chính bạn từ lịch, email, Jira, Confluence, SDP và Teams. '
                    'Thông tin khách hàng được che trước khi gửi tới mô hình AI nội bộ.',
                    textAlign: TextAlign.center,
                    style: t.textTheme.bodyMedium?.copyWith(color: AppColors.muted, height: 1.4),
                  ),
                  const SizedBox(height: 24),
                  Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [
                    for (final s in _suggestions) ActionChip(label: Text(s), onPressed: () => _send(s)),
                  ]),
                ])
              : ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                  itemCount: turns.length + (busy ? 1 : 0),
                  itemBuilder: (ctx, i) => i == turns.length ? const _Typing() : _Bubble(turn: turns[i]),
                ),
        ),
        SafeArea(
          top: false,
          child: Container(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
            decoration: BoxDecoration(border: Border(top: BorderSide(color: t.dividerTheme.color!))),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: _input,
                  minLines: 1,
                  maxLines: 4,
                  maxLength: 500,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  decoration: const InputDecoration(
                    hintText: 'Ví dụ: Tuần này tôi còn ticket nào quá hạn?',
                    counterText: '',
                    contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                onPressed: busy ? null : () => _send(),
                icon: const Icon(Icons.arrow_upward),
                tooltip: 'Gửi',
              ),
            ]),
          ),
        ),
      ]),
    );
  }
}

class _Bubble extends ConsumerWidget {
  const _Bubble({required this.turn});
  final ChatTurn turn;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    if (turn.fromUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(bottom: 12, left: 48),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(color: t.colorScheme.primary, borderRadius: BorderRadius.circular(16)),
          child: Text(turn.text, style: TextStyle(color: t.colorScheme.onPrimary)),
        ),
      );
    }
    final r = turn.result;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16, right: 24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: turn.error ? Severity.soft('critical', t.brightness) : t.cardTheme.color,
            border: Border.all(color: t.dividerTheme.color!),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (r != null) ...[AiBadge(byAi: r.generatedBy == 'llm'), const SizedBox(height: 8)],
            SelectableText(turn.text, style: const TextStyle(height: 1.45)),
          ]),
        ),
        if (r != null && r.items.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final it in r.items.take(5)) ...[
            WorkItemTile(item: it, onTap: () => showItemSheet(context, it)),
            const SizedBox(height: 8),
          ],
        ],
      ]),
    );
  }
}

class _Typing extends StatelessWidget {
  const _Typing();

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: Row(children: [
          SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Theme.of(context).colorScheme.secondary)),
          const SizedBox(width: 10),
          const Text('Đang tìm trong dữ liệu công việc…', style: TextStyle(color: AppColors.muted)),
        ]),
      );
}
