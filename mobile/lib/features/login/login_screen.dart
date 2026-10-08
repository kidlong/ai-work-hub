import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../core/api_client.dart';
import '../../data/providers.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _form = GlobalKey<FormState>();
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authProvider.notifier).login(_user.text, _pass.text);
    } catch (e) {
      setState(() => _error = ApiException.from(e).message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final notice = ref.watch(authProvider).message;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _form,
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(color: AppColors.ink, borderRadius: BorderRadius.circular(16)),
                      child: const Icon(Icons.hub, color: Color(0xFF7EE0D3), size: 30),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text('AI Work Hub', style: t.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -0.5)),
                  const SizedBox(height: 6),
                  Text('Lịch, email, Jira, Confluence, ServiceDesk và Teams — gom về một nơi, AI sắp xếp giúp bạn.',
                      style: t.textTheme.bodyLarge?.copyWith(color: AppColors.muted, height: 1.4)),
                  const SizedBox(height: 32),
                  if (notice != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(color: AppColors.infoSoft, borderRadius: BorderRadius.circular(12)),
                      child: Text(notice, style: const TextStyle(color: AppColors.info)),
                    ),
                    const SizedBox(height: 16),
                  ],
                  TextFormField(
                    controller: _user,
                    autofillHints: const [AutofillHints.username],
                    textInputAction: TextInputAction.next,
                    autocorrect: false,
                    decoration: const InputDecoration(labelText: 'Tài khoản AD', hintText: 'vd: an.nguyen', prefixIcon: Icon(Icons.person_outline)),
                    validator: (v) => (v == null || v.trim().length < 2) ? 'Nhập tài khoản' : null,
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _pass,
                    obscureText: _obscure,
                    autofillHints: const [AutofillHints.password],
                    onFieldSubmitted: (_) => _submit(),
                    decoration: InputDecoration(
                      labelText: 'Mật khẩu',
                      prefixIcon: const Icon(Icons.lock_outline),
                      suffixIcon: IconButton(
                        onPressed: () => setState(() => _obscure = !_obscure),
                        icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                        tooltip: _obscure ? 'Hiện mật khẩu' : 'Ẩn mật khẩu',
                      ),
                    ),
                    validator: (v) => (v == null || v.isEmpty) ? 'Nhập mật khẩu' : null,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: AppColors.critical)),
                  ],
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Text('Đăng nhập'),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    'Đăng nhập bằng tài khoản Active Directory của ngân hàng. Yêu cầu kết nối mạng nội bộ hoặc VPN.\n'
                    'Môi trường demo: an.nguyen / demo hoặc lan.pham / demo',
                    textAlign: TextAlign.center,
                    style: t.textTheme.bodySmall?.copyWith(color: AppColors.muted, height: 1.5),
                  ),
                ]),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class LockScreen extends ConsumerStatefulWidget {
  const LockScreen({super.key});

  @override
  ConsumerState<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends ConsumerState<LockScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => ref.read(authProvider.notifier).unlock());
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.fingerprint, size: 72, color: t.colorScheme.secondary),
              const SizedBox(height: 16),
              Text('AI Work Hub đang khoá', style: t.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 8),
              const Text('Xác thực sinh trắc học để tiếp tục.', style: TextStyle(color: AppColors.muted)),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: () => ref.read(authProvider.notifier).unlock(),
                icon: const Icon(Icons.lock_open),
                label: const Text('Mở khoá'),
              ),
              TextButton(
                onPressed: () => ref.read(authProvider.notifier).logout(),
                child: const Text('Đăng nhập bằng tài khoản khác'),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
