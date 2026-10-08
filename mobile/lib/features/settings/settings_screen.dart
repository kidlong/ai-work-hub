import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../data/live_events.dart';
import '../../data/providers.dart';
import '../../domain/models.dart';
import '../../widgets/common.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  UserSettings? _draft;
  bool _saving = false;
  bool? _biometric;
  bool? _details;
  bool _canBiometric = false;

  @override
  void initState() {
    super.initState();
    _loadLocal();
  }

  Future<void> _loadLocal() async {
    final store = ref.read(secureStoreProvider);
    final b = await store.biometricLock;
    final d = await store.notificationDetails;
    final can = await ref.read(authProvider.notifier).canUseBiometric();
    if (mounted) {
      setState(() {
        _biometric = b;
        _details = d;
        _canBiometric = can;
      });
    }
  }

  Future<void> _save(UserSettings s) async {
    setState(() {
      _draft = s;
      _saving = true;
    });
    try {
      final saved = await ref.read(repositoryProvider).saveSettings(s);
      setState(() => _draft = saved);
      refreshWorkData(ref);
      ref.invalidate(sourcesProvider);
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<String?> _pickTime(String current) async {
    final p = current.split(':');
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: int.parse(p[0]), minute: int.parse(p[1])),
      builder: (ctx, child) => MediaQuery(data: MediaQuery.of(ctx).copyWith(alwaysUse24HourFormat: true), child: child!),
    );
    if (picked == null) return null;
    return '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';
  }

  Future<void> _addVip(UserSettings s) async {
    final c = TextEditingController();
    final v = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Thêm người gửi ưu tiên'),
        content: TextField(
          controller: c,
          autofocus: true,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(hintText: 'email hoặc tên miền, vd: congty-abc.vn'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Huỷ')),
          FilledButton(onPressed: () => Navigator.pop(ctx, c.text.trim().toLowerCase()), child: const Text('Thêm')),
        ],
      ),
    );
    if (v != null && v.isNotEmpty && !s.vipSenders.contains(v)) {
      await _save(s.copyWith(vipSenders: [...s.vipSenders, v]));
    }
  }

  Future<void> _emitSim([String? scenario]) async {
    try {
      await ref.read(repositoryProvider).simEmit(scenario: scenario);
      await ref.read(liveEventsProvider.notifier).poll(); // hiện banner ngay, không đợi nhịp 8 giây
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    }
  }

  Future<void> _pickScenario() async {
    try {
      final list = await ref.read(repositoryProvider).simScenarios();
      if (!mounted) return;
      final key = await showModalBottomSheet<String>(
        context: context,
        builder: (ctx) => SafeArea(
          child: ListView(shrinkWrap: true, children: [
            for (final sc in list) ListTile(title: Text(sc.label), onTap: () => Navigator.pop(ctx, sc.key)),
          ]),
        ),
      );
      if (key != null) await _emitSim(key);
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    }
  }

  Future<void> _resetSim() async {
    try {
      await ref.read(repositoryProvider).simReset();
      refreshWorkData(ref);
      if (mounted) showSnack(context, 'Đã đặt lại dữ liệu giả lập');
    } catch (e) {
      if (mounted) showSnack(context, ApiException.from(e).message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final remote = ref.watch(settingsProvider);
    final sources = ref.watch(sourcesProvider);
    final today = ref.watch(todayProvider).value;
    final t = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Cài đặt'),
        actions: [if (_saving) const Padding(padding: EdgeInsets.all(16), child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))],
      ),
      body: AsyncBody(
        value: remote,
        onRetry: () => ref.invalidate(settingsProvider),
        data: (fetched) {
          final s = _draft ?? fetched;
          return ListView(padding: const EdgeInsets.fromLTRB(16, 4, 16, 40), children: [
            if (today != null)
              Card(
                child: ListTile(
                  contentPadding: const EdgeInsets.all(14),
                  leading: CircleAvatar(
                    backgroundColor: t.colorScheme.primary,
                    child: Text(today.user.initials, style: TextStyle(color: t.colorScheme.onPrimary)),
                  ),
                  title: Text(today.user.displayName, style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Text([today.user.title, today.user.department].where((e) => e.isNotEmpty).join('\n')),
                ),
              ),

            const SectionHeader('Nguồn dữ liệu', icon: Icons.hub_outlined),
            Card(
              child: sources.when(
                loading: () => const Padding(padding: EdgeInsets.all(20), child: Center(child: CircularProgressIndicator())),
                error: (e, _) => ListTile(title: Text(ApiException.from(e).message)),
                data: (list) => Column(children: [
                  for (final src in list)
                    SwitchListTile(
                      value: s.enabledSources.contains(src.id),
                      onChanged: !src.available
                          ? null
                          : (v) => _save(s.copyWith(
                                enabledSources: v
                                    ? [...s.enabledSources, src.id]
                                    : s.enabledSources.where((e) => e != src.id).toList(),
                              )),
                      title: Text(src.name),
                      subtitle: src.available ? null : const Text('Chưa được quản trị viên kết nối'),
                    ),
                ]),
              ),
            ),

            const SectionHeader('Nhắc việc', icon: Icons.notifications_outlined),
            Card(
              child: Column(children: [
                ListTile(
                  title: const Text('Nhắc trước cuộc họp'),
                  trailing: DropdownButton<int>(
                    value: s.meetingLeadMinutes,
                    underline: const SizedBox.shrink(),
                    items: [for (final m in {5, 10, 15, 30, s.meetingLeadMinutes}) DropdownMenuItem(value: m, child: Text('$m phút'))],
                    onChanged: (v) => v == null ? null : _save(s.copyWith(meetingLeadMinutes: v)),
                  ),
                ),
                const Divider(indent: 16, endIndent: 16),
                ListTile(
                  title: const Text('Giờ nhận Morning Brief'),
                  subtitle: const Text('Từ thứ 2 đến thứ 6'),
                  trailing: Text(s.briefTime, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                  onTap: () async {
                    final v = await _pickTime(s.briefTime);
                    if (v != null) await _save(s.copyWith(briefTime: v));
                  },
                ),
                const Divider(indent: 16, endIndent: 16),
                ListTile(
                  title: const Text('Giờ yên lặng'),
                  subtitle: const Text('Chỉ nhắc mức khẩn (vi phạm SLA, quá hạn nghiêm trọng)'),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    TextButton(
                      onPressed: () async {
                        final v = await _pickTime(s.quietStart);
                        if (v != null) await _save(s.copyWith(quietStart: v));
                      },
                      child: Text(s.quietStart),
                    ),
                    const Text('–'),
                    TextButton(
                      onPressed: () async {
                        final v = await _pickTime(s.quietEnd);
                        if (v != null) await _save(s.copyWith(quietEnd: v));
                      },
                      child: Text(s.quietEnd),
                    ),
                  ]),
                ),
              ]),
            ),

            SectionHeader('Người gửi / khách hàng ưu tiên', icon: Icons.star_outline,
                trailing: IconButton(onPressed: () => _addVip(s), icon: const Icon(Icons.add), tooltip: 'Thêm')),
            if (s.vipSenders.isEmpty)
              Text('Email hoặc tên miền của khách hàng VIP. Thư từ họ được ưu tiên và nhắc ngay.',
                  style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted))
            else
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final v in s.vipSenders)
                  InputChip(
                    label: Text(v),
                    onDeleted: () => _save(s.copyWith(vipSenders: s.vipSenders.where((e) => e != v).toList())),
                  ),
              ]),

            if (ref.watch(liveEventsProvider).available == true) ...[
              const SectionHeader('Dữ liệu giả lập', icon: Icons.bolt_outlined),
              Card(
                child: Column(children: [
                  SwitchListTile(
                    value: s.liveSimEnabled,
                    onChanged: (v) => _save(s.copyWith(liveSimEnabled: v)),
                    title: const Text('Tự động phát sự kiện mới'),
                    subtitle: const Text('Cứ 30–90 giây có thêm mail, ticket, họp... (chế độ MOCK)'),
                  ),
                  ListTile(
                    leading: const Icon(Icons.flash_on_outlined),
                    title: const Text('Phát sự kiện ngay'),
                    onTap: _emitSim,
                  ),
                  ListTile(
                    leading: const Icon(Icons.list_alt_outlined),
                    title: const Text('Chọn kịch bản...'),
                    onTap: _pickScenario,
                  ),
                  ListTile(
                    leading: const Icon(Icons.restart_alt),
                    title: const Text('Đặt lại dữ liệu giả lập'),
                    onTap: _resetSim,
                  ),
                ]),
              ),
            ],

            const SectionHeader('Bảo mật & quyền riêng tư', icon: Icons.shield_outlined),
            Card(
              child: Column(children: [
                SwitchListTile(
                  value: _biometric ?? false,
                  onChanged: !_canBiometric || _biometric == null
                      ? null
                      : (v) async {
                          await ref.read(secureStoreProvider).setBiometricLock(v);
                          setState(() => _biometric = v);
                        },
                  title: const Text('Khoá bằng sinh trắc học'),
                  subtitle: Text(_canBiometric ? 'Yêu cầu vân tay/Face ID khi mở app' : 'Thiết bị không hỗ trợ'),
                ),
                SwitchListTile(
                  value: _details ?? false,
                  onChanged: _details == null
                      ? null
                      : (v) async {
                          await ref.read(secureStoreProvider).setNotificationDetails(v);
                          setState(() => _details = v);
                          ref.read(notificationSyncProvider).resync().ignore();
                        },
                  title: const Text('Hiện chi tiết trong thông báo'),
                  subtitle: const Text('Tắt để không lộ tiêu đề công việc trên màn hình khoá'),
                ),
              ]),
            ),

            const SizedBox(height: 24),
            OutlinedButton.icon(
              onPressed: () async {
                try {
                  await ref.read(repositoryProvider).syncNow();
                  refreshWorkData(ref);
                  if (context.mounted) showSnack(context, 'Đã đồng bộ dữ liệu mới nhất');
                } catch (e) {
                  if (context.mounted) showSnack(context, ApiException.from(e).message);
                }
              },
              icon: const Icon(Icons.sync),
              label: const Text('Đồng bộ ngay'),
            ),
            const SizedBox(height: 10),
            TextButton.icon(
              style: TextButton.styleFrom(foregroundColor: AppColors.critical),
              onPressed: () => ref.read(authProvider.notifier).logout(),
              icon: const Icon(Icons.logout),
              label: const Text('Đăng xuất'),
            ),
          ]);
        },
      ),
    );
  }
}
