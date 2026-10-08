import 'package:dio/dio.dart';

import 'auth/secure_store.dart';
import 'config.dart';

class ApiException implements Exception {
  ApiException(this.message, [this.statusCode]);
  final String message;
  final int? statusCode;

  @override
  String toString() => message;

  static ApiException from(Object e) {
    if (e is ApiException) return e;
    if (e is DioException) {
      final data = e.response?.data;
      final detail = data is Map ? data['detail'] : null;
      if (detail is String) return ApiException(detail, e.response?.statusCode);
      switch (e.type) {
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.receiveTimeout:
        case DioExceptionType.sendTimeout:
          return ApiException('Máy chủ phản hồi chậm, vui lòng thử lại.');
        case DioExceptionType.connectionError:
          return ApiException('Không kết nối được máy chủ. Kiểm tra VPN/mạng nội bộ.');
        default:
          return ApiException('Có lỗi xảy ra (${e.response?.statusCode ?? 'mạng'}).', e.response?.statusCode);
      }
    }
    return ApiException('Có lỗi xảy ra: $e');
  }
}

/// Dio client: gắn access token, tự refresh 1 lần khi gặp 401, báo hết phiên nếu refresh hỏng.
class ApiClient {
  ApiClient(this._store, {required this.onSessionExpired, Dio? dio})
      : dio = dio ??
            Dio(BaseOptions(
              baseUrl: AppConfig.apiBaseUrl,
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 60),
              contentType: 'application/json',
            )) {
    this.dio.interceptors.add(QueuedInterceptorsWrapper(
          onRequest: (options, handler) async {
            final token = await _store.accessToken;
            if (token != null && !options.path.startsWith('/auth/login')) {
              options.headers['Authorization'] = 'Bearer $token';
            }
            handler.next(options);
          },
          onError: (err, handler) async {
            final path = err.requestOptions.path;
            final retried = err.requestOptions.extra['retried'] == true;
            if (err.response?.statusCode == 401 && !path.startsWith('/auth/') && !retried) {
              if (await _tryRefresh()) {
                final opts = err.requestOptions
                  ..extra['retried'] = true
                  ..headers['Authorization'] = 'Bearer ${await _store.accessToken}';
                try {
                  return handler.resolve(await this.dio.fetch(opts));
                } on DioException catch (e) {
                  return handler.next(e);
                }
              }
              onSessionExpired();
            }
            handler.next(err);
          },
        ));
  }

  final SecureStore _store;
  final Dio dio;
  final void Function() onSessionExpired;

  Future<bool> _tryRefresh() async {
    final refresh = await _store.refreshToken;
    if (refresh == null) return false;
    try {
      final r = await Dio(BaseOptions(baseUrl: AppConfig.apiBaseUrl))
          .post('/auth/refresh', data: {'refresh_token': refresh});
      await _store.saveTokens(r.data['access_token'] as String, r.data['refresh_token'] as String);
      return true;
    } catch (_) {
      return false;
    }
  }
}
