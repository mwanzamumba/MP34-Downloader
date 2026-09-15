import 'package:dio/dio.dart';

import '../models/analyser.dart';

class MediaApi {
  static const String baseUrl =
      'https://mp34-downloader-api.onrender.com';

  final Dio _dio;

  MediaApi()
      : _dio = Dio(
          BaseOptions(
            baseUrl: baseUrl,
            connectTimeout:
                const Duration(seconds: 30),
            receiveTimeout:
                const Duration(minutes: 30),
            sendTimeout:
                const Duration(seconds: 30),
            headers: {
              'Accept': '*/*',
              'User-Agent':
                  'facebookexternalhit/1.1',
            },
          ),
        );

  // ============================================================
  // ANALYZE URL
  // ============================================================

  Future<MediaAnalysis> analyze(
    String url,
  ) async {
    final response = await _dio.post(
      '/analyze',
      data: {
        'url': url,
      },
    );

    return MediaAnalysis.fromJson(
      Map<String, dynamic>.from(
        response.data,
      ),
    );
  }

  // ============================================================
  // DOWNLOAD VIDEO STREAM
  // ============================================================

  Future<void> downloadVideo({
    required MediaAnalysis media,
    required String savePath,
    required CancelToken cancelToken,
    required void Function(
      int received,
      int total,
    ) onProgress,
  }) async {
    await _dio.download(
      media.video.url,
      savePath,
      cancelToken: cancelToken,
      onReceiveProgress: onProgress,
      options: Options(
        headers: {
          'Accept': '*/*',
          'User-Agent':
              'facebookexternalhit/1.1',
        },
      ),
    );
  }

  // ============================================================
  // DOWNLOAD AUDIO STREAM
  // ============================================================

  Future<void> downloadAudio({
    required MediaAnalysis media,
    required String savePath,
    required CancelToken cancelToken,
    required void Function(
      int received,
      int total,
    ) onProgress,
  }) async {
    await _dio.download(
      media.audio.url,
      savePath,
      cancelToken: cancelToken,
      onReceiveProgress: onProgress,
      options: Options(
        headers: {
          'Accept': '*/*',
          'User-Agent':
              'facebookexternalhit/1.1',
        },
      ),
    );
  }
}