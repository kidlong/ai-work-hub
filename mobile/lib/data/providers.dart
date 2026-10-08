import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';

import '../core/api_client.dart';
import '../core/auth/secure_store.dart';
import '../core/config.dart';
import '../core/notifications/local_notifications.dart';
import '../core/notifications/notification_planner.dart';
import '../domain/models.dart';
import 'repository.dart';

// ---------------------------------------------------------------- Hạ tầng

final secureStoreProvider = Provider<SecureStore>((ref) => SecureStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(
    ref.watch(secureStoreProvider),
    onSessionExpired: () => ref.read(authProvider.notifier).sessionExpired(),
  );
});

final repositoryProvider = Provider<WorkHubRepository>((ref) => WorkHubRepository(ref.watch(apiClientProvider).dio));

// ---------------------------------------------------------------- Xác thực

enum AuthStatus { unknown, signedOut, locked, signedIn }

class AuthState {
  const AuthState(this.status, {this.message});
  final AuthStatus status;
  final String? message;
}

class AuthController extends Notifier<AuthState> {
  final _localAuth = LocalAuthentication();
  DateTime? _pausedAt;

  @override
  AuthState build() {
    Future.microtask(_restore);
    return const AuthState(AuthStatus.unknown);
  }

  SecureStore get _store => ref.read(secureStoreProvider);

  Future<void> _restore() async {
    final token = await _store.refreshToken;
    if (token == null) {
      state = const AuthState(AuthStatus.signedOut);
    } else if (await _store.biometricLock) {
      state = const AuthState(AuthStatus.locked);
    } else {
      state = const AuthState(AuthStatus.signedIn);
    }
  }

  Future<void> login(String username, String password) async {
    final tokens = await ref.read(repositoryProvider).login(username.trim(), password);
    await _store.saveTokens(tokens['access_token'] as String, tokens['refresh_token'] as String);
    state = const AuthState(AuthStatus.signedIn);
    await LocalNotifications.instance.requestPermission();
  }

  Future<bool> unlock() async {
    try {
      final ok = await _localAuth.authenticate(
        localizedReason: 'Xác thực để mở AI Work Hub',
        persistAcrossBackgrounding: true,
      );
      if (ok) state = const AuthState(AuthStatus.signedIn);
      return ok;
    } catch (_) {
      return false;
    }
  }

  Future<bool> canUseBiometric() async {
    try {
      return await _localAuth.isDeviceSupported();
    } catch (_) {
      return false;
    }
  }

  /// Gọi từ vòng đời app: khoá lại nếu app ở nền quá lâu.
  void onPaused() => _pausedAt = DateTime.now();

  Future<void> onResumed() async {
    final paused = _pausedAt;
    _pausedAt = null;
    if (state.status != AuthStatus.signedIn || paused == null) return;
    if (DateTime.now().difference(paused) >= AppConfig.autoLockAfter && await _store.biometricLock) {
      state = const AuthState(AuthStatus.locked);
    }
  }

  void sessionExpired() {
    if (state.status == AuthStatus.signedOut) return;
    _store.clearTokens();
    state = const AuthState(AuthStatus.signedOut, message: 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
  }

  Future<void> logout() async {
    await _store.clearTokens();
    await LocalNotifications.instance.clear();
    state = const AuthState(AuthStatus.signedOut);
  }
}

final authProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);

// ---------------------------------------------------------------- Dữ liệu

final todayProvider = FutureProvider.autoDispose<TodayData>((ref) => ref.watch(repositoryProvider).today());

final alertsProvider =
    FutureProvider.autoDispose.family<List<AlertModel>, String>((ref, scope) => ref.watch(repositoryProvider).alerts(scope: scope));

final briefProvider = FutureProvider.autoDispose<DailyBrief>((ref) => ref.watch(repositoryProvider).brief());

final meetingPrepProvider =
    FutureProvider.autoDispose.family<MeetingPrep, int>((ref, id) => ref.watch(repositoryProvider).meetingPrep(id));

final workItemProvider =
    FutureProvider.autoDispose.family<WorkItem, int>((ref, id) => ref.watch(repositoryProvider).workItem(id));

final sourcesProvider = FutureProvider.autoDispose<List<SourceInfo>>((ref) => ref.watch(repositoryProvider).sources());

final settingsProvider = FutureProvider.autoDispose<UserSettings>((ref) => ref.watch(repositoryProvider).settings());

/// Làm mới mọi màn hình phụ thuộc dữ liệu công việc sau khi người dùng thao tác.
void refreshWorkData(WidgetRef ref) {
  ref.invalidate(todayProvider);
  ref.invalidate(alertsProvider);
  ref.invalidate(briefProvider);
  ref.read(notificationSyncProvider).resync().ignore();
}

// ---------------------------------------------------------------- Lịch nhắc cục bộ

final notificationSyncProvider = Provider<NotificationSync>((ref) => NotificationSync(ref));

class NotificationSync {
  NotificationSync(this._ref);
  final Ref _ref;

  /// Tải nhắc sắp tới từ backend và lên lịch lại trên máy.
  Future<int> resync() async {
    final repo = _ref.read(repositoryProvider);
    final store = _ref.read(secureStoreProvider);
    final upcoming = await repo.alerts(scope: 'upcoming');
    String? briefTime;
    try {
      briefTime = (await repo.settings()).briefTime;
    } catch (_) {}
    final plan = planNotifications(
      upcoming,
      DateTime.now(),
      showDetails: await store.notificationDetails,
      maxCount: AppConfig.maxScheduledNotifications,
      briefTime: briefTime,
    );
    return LocalNotifications.instance.apply(plan);
  }
}
