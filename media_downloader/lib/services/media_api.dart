import 'package:dio/dio.dart';
import 'package:media_downloader/models/analyser.dart';

class MediaApi {
  MediaApi({Dio? client})
    : _client = client ??
          Dio(
            BaseOptions(
              baseUrl: _baseUrl,
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 30),
            ),
          );

  static const _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
  final Dio _client;
  Future<MediaInfo> analyse(String url) async {
    try {
      final response = await _client.post<Map<String, dynamic>>('/analyze', data: {'url': url});
      return MediaInfo.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw MediaApiException(_messageFor(error));
    }
  }
  Future<DownloadResult> download(String url) async {
    try {
      final response = await _client.post<Map<String, dynamic>>('/download', data: {'url': url});
      return DownloadResult.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw MediaApiException(_messageFor(error));
    }
  }
  String _messageFor(DioException error) {
    final data = error.response?.data;
    if (data is Map && data['detail'] is String) return data['detail'] as String;
    return 'Could not reach the backend. Start it and check API_BASE_URL.';
  }
}
class MediaApiException implements Exception {
  const MediaApiException(this.message);
  final String message;
}
class DownloadResult {
  const DownloadResult({required this.fileName});
  final String fileName;
  factory DownloadResult.fromJson(Map<String, dynamic> json) =>
      DownloadResult(fileName: json['file_name'] as String? ?? 'media file');
}
