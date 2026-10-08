import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../domain/models.dart';
import 'providers.dart';

const liveBaseInterval = Duration(seconds: 8);
const liveMaxInterval = Duration(seconds: 30);

/// `available`: null = chưa biết, true = backend có mô phỏng, false = backend không bật (404).
/// Mỗi lần có lô sự kiện mới `seq` tăng lên để UI biết mà phản ứng (invalidate provider, hiện banner).
class LiveFeedState {
  const LiveFeedState({this.available, this.batch = const [], this.seq = 0});

  final bool? available;
  final List<LiveEvent> batch;
  final int seq;

  LiveFeedState copyWith({bool? available}) =>
      LiveFeedState(available: available ?? this.available, batch: batch, seq: seq);
}

String liveBannerText(List<LiveEvent> batch) {
  if (batch.isEmpty) return '';
  if (batch.length == 1) return batch.single.title;
  return '${batch.length} mục mới · ${batch.last.title}';
}

/// Poll `/events?since=` khi app mở. Chỉ lo việc lấy sự kiện; làm mới màn hình và banner do `app.dart` xử lý.
class LiveEventsController extends Notifier<LiveFeedState> {
  Timer? _timer;
  int? _cursor;
  bool _running = false;
  bool _busy = false;
  bool _disposed = false;
  Duration _interval = liveBaseInterval;

  Duration get interval => _interval;

  @override
  LiveFeedState build() {
    ref.onDispose(() {
      _disposed = true;
      _running = false;
      _timer?.cancel();
    });
    return const LiveFeedState();
  }

  void start() {
    if (_running || state.available == false) return;
    _running = true;
    _loop();
  }

  void stop() {
    _running = false;
    _timer?.cancel();
    _timer = null;
  }

  /// Đăng xuất: quên con trỏ và trạng thái để phiên sau bắt đầu sạch.
  void reset() {
    stop();
    _cursor = null;
    _interval = liveBaseInterval;
    state = const LiveFeedState();
  }

  Future<void> _loop() async {
    await poll();
    if (!_running || _disposed) return;
    _timer = Timer(_interval, _loop);
  }

  Future<void> poll() async {
    if (_busy || _disposed || state.available == false) return;
    _busy = true;
    try {
      final since = _cursor;
      final page = await ref.read(repositoryProvider).liveEvents(since: since);
      if (_disposed) return;
      _interval = liveBaseInterval;
      if (state.available != true) state = state.copyWith(available: true);
      if (since == null || page.latestId < since) {
        _cursor = page.latestId; // lần đầu, hoặc server đã reset: lấy con trỏ mới, không phát lại
        return;
      }
      if (page.events.isEmpty) return;
      _cursor = page.events.last.id;
      state = LiveFeedState(available: true, batch: page.events, seq: state.seq + 1);
    } on ApiException catch (e) {
      if (_disposed) return;
      if (e.statusCode == 404) {
        stop();
        state = state.copyWith(available: false);
      } else {
        final next = _interval * 2;
        _interval = next > liveMaxInterval ? liveMaxInterval : next;
      }
    } finally {
      _busy = false;
    }
  }
}

final liveEventsProvider = NotifierProvider<LiveEventsController, LiveFeedState>(LiveEventsController.new);
