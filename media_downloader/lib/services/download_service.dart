import 'package:dio/dio.dart';

import 'download_service_android.dart'
  if (dart.library.html) 'download_service_web.dart';

class DownloadService {
  static Future<void> download({
    required dynamic media,
    required String sourceUrl,
    required String format,
    required CancelToken cancelToken,
    required void Function(
      double progress,
      String status,
    ) onProgress,
  }) async {
    await downloadPlatform(
      media: media,
      sourceUrl: sourceUrl,
      format: format,
      cancelToken: cancelToken,
      onProgress: onProgress,
    );
  }
}