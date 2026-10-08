import 'package:dio/dio.dart';

import '../core/api_client.dart';
import '../domain/models.dart';

/// Toàn bộ lời gọi BFF. App không kết nối trực tiếp tới Exchange/Jira/SDP.
class WorkHubRepository {
  WorkHubRepository(this._dio);

  final Dio _dio;

  Future<T> _call<T>(Future<T> Function() fn) async {
    try {
      return await fn();
    } catch (e) {
      throw ApiException.from(e);
    }
  }

  Future<Map<String, dynamic>> login(String username, String password) => _call(() async {
        final r = await _dio.post('/auth/login', data: {'username': username, 'password': password});
        return Map<String, dynamic>.from(r.data as Map);
      });

  Future<UserProfile> me() => _call(() async => UserProfile.fromJson((await _dio.get('/auth/me')).data));

  Future<TodayData> today() => _call(() async => TodayData.fromJson((await _dio.get('/today')).data));

  Future<List<WorkItem>> workItems({String? source, String? kind, String? query}) => _call(() async {
        final r = await _dio.get('/work-items', queryParameters: {
          'source': ?source,
          'kind': ?kind,
          'q': ?query,
        });
        return (r.data as List).map((e) => WorkItem.fromJson(e as Map<String, dynamic>)).toList();
      });

  Future<WorkItem> workItem(int id) =>
      _call(() async => WorkItem.fromJson((await _dio.get('/work-items/$id')).data));

  Future<WorkItem> markDone(int id) =>
      _call(() async => WorkItem.fromJson((await _dio.post('/work-items/$id/done')).data));

  Future<WorkItem> markUndone(int id) =>
      _call(() async => WorkItem.fromJson((await _dio.post('/work-items/$id/undone')).data));

  Future<WorkItem> snoozeItem(int id, Duration d) => _call(() async =>
      WorkItem.fromJson((await _dio.post('/work-items/$id/snooze', data: {'minutes': d.inMinutes})).data));

  Future<List<AlertModel>> alerts({String scope = 'active'}) => _call(() async {
        final r = await _dio.get('/alerts', queryParameters: {'scope': scope});
        return (r.data as List).map((e) => AlertModel.fromJson(e as Map<String, dynamic>)).toList();
      });

  Future<void> ackAlert(int id) => _call(() => _dio.post('/alerts/$id/ack'));

  Future<void> ackAll() => _call(() => _dio.post('/alerts/ack-all'));

  Future<void> snoozeAlert(int id, Duration d) =>
      _call(() => _dio.post('/alerts/$id/snooze', data: {'minutes': d.inMinutes}));

  Future<DailyBrief> brief({bool regenerate = false}) => _call(() async {
        final r = regenerate ? await _dio.post('/brief/regenerate') : await _dio.get('/brief/today');
        return DailyBrief.fromJson(r.data as Map<String, dynamic>);
      });

  Future<MeetingPrep> meetingPrep(int itemId) =>
      _call(() async => MeetingPrep.fromJson((await _dio.get('/meetings/$itemId/prep')).data));

  Future<AskResult> ask(String question) =>
      _call(() async => AskResult.fromJson((await _dio.post('/ask', data: {'question': question})).data));

  Future<UserSettings> settings() =>
      _call(() async => UserSettings.fromJson((await _dio.get('/settings')).data));

  Future<UserSettings> saveSettings(UserSettings s) =>
      _call(() async => UserSettings.fromJson((await _dio.put('/settings', data: s.toJson())).data));

  Future<List<SourceInfo>> sources() => _call(() async =>
      ((await _dio.get('/sources')).data as List).map((e) => SourceInfo.fromJson(e as Map<String, dynamic>)).toList());

  Future<void> syncNow() => _call(() => _dio.post('/sync'));

  Future<void> registerDevice(String token, String platform) =>
      _call(() => _dio.post('/devices', data: {'token': token, 'platform': platform}));
}
