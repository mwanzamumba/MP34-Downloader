import 'package:dio/dio.dart';

import '../models/analyser.dart';

class MediaApi {
  final Dio _dio = Dio(
    BaseOptions(
      baseUrl:
          'https://mp34-downloader-api.onrender.com',

      connectTimeout:
          const Duration(seconds: 30),

      sendTimeout:
          const Duration(seconds: 30),

      receiveTimeout:
          const Duration(minutes: 10),

      headers: {
        'User-Agent':
            'Mozilla/5.0 (Android) MP34Downloader',
        'Accept': '*/*',
      },
    ),
  );

  // ============================================================
  // ANALYZE MEDIA
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

    if (response.statusCode != 200) {
      throw Exception(
        'Analysis failed: HTTP ${response.statusCode}',
      );
    }

    if (response.data is! Map) {
      throw Exception(
        'The server returned an invalid response.',
      );
    }

    return MediaAnalysis.fromJson(
      Map<String, dynamic>.from(
        response.data as Map,
      ),
    );
  }

  // ============================================================
  // DOWNLOAD DIRECT MEDIA STREAM
  // ============================================================

  Future<void> downloadStream({
    required String url,
    required String savePath,
    required CancelToken cancelToken,
    required void Function(
      int received,
      int total,
    ) onProgress,
  }) async {
    await _dio.download(
      url,
      savePath,

      cancelToken: cancelToken,

      onReceiveProgress:
          onProgress,

      options: Options(
        headers: {
          'User-Agent':
              'Mozilla/5.0 (Android) MP34Downloader',
          'Accept': '*/*',
        },

        followRedirects: true,

        maxRedirects: 10,

        responseType:
            ResponseType.bytes,

        validateStatus: (status) {
          return status != null &&
              status >= 200 &&
              status < 400;
        },
      ),
    );
  }
}