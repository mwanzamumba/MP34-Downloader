import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';

import 'media_store_service.dart';
import 'notification_service.dart';
import 'media_api.dart';

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
    final tempDirectory =
        await getTemporaryDirectory();

    final safeName = _safeFileName(media.title);

    final timestamp =
        DateTime.now().millisecondsSinceEpoch;

    final extension =
        format == 'mp3' ? 'mp3' : 'mp4';

    final outputPath =
        '${tempDirectory.path}/'
        '${safeName}_$timestamp.$extension';

    try {
      // ============================================================
      // START NOTIFICATION
      // ============================================================

      await NotificationService.showStarted(
        title: media.title,
        format: format.toUpperCase(),
      );

      onProgress(
        0.02,
        'Preparing download...',
      );

      // ============================================================
      // CALL BACKEND
      // ============================================================

      final MediaApi api = MediaApi();

      print('');
      print('========================================');
      print('BACKEND DOWNLOAD');
      print('========================================');
      print('Title: ${media.title}');
      print('Format: $format');
      print('Source URL: $sourceUrl');
      print('========================================');

      final String formatId =
          _getFormatId(
        media,
        format,
      );

      print('Format ID: $formatId');

      /*
       * The Render backend performs the actual
       * yt-dlp download and FFmpeg processing.
       *
       * Flutter only receives the final file URL.
       */

      final String downloadUrl =
          await api.download(
        url: sourceUrl,
        formatId: formatId,
        mediaType:
            format == 'mp3'
                ? 'audio'
                : 'video',
        audioFormat:
            format == 'mp3'
                ? 'mp3'
                : null,
      );

      if (cancelToken.isCancelled) {
        throw DioException(
          requestOptions:
              RequestOptions(path: ''),
          type: DioExceptionType.cancel,
        );
      }

      print('');
      print('========================================');
      print('BACKEND FILE READY');
      print('========================================');
      print('Download URL: $downloadUrl');
      print('========================================');

      // ============================================================
      // DOWNLOAD FINAL FILE FROM SERVER
      // ============================================================

      onProgress(
        0.25,
        'Downloading ${format.toUpperCase()}...',
      );

      await _downloadFinalFile(
        url: downloadUrl,
        path: outputPath,
        cancelToken: cancelToken,
        onProgress: (value) {
          final progress =
              0.25 + (value * 0.70);

          onProgress(
            progress.clamp(
              0.25,
              0.95,
            ),
            'Downloading '
            '${format.toUpperCase()}... '
            '${(value * 100).round()}%',
          );
        },
      );

      if (cancelToken.isCancelled) {
        throw DioException(
          requestOptions:
              RequestOptions(path: ''),
          type: DioExceptionType.cancel,
        );
      }

      // ============================================================
      // VERIFY FILE
      // ============================================================

      final file = File(outputPath);

      final exists = await file.exists();

      print('');
      print('========================================');
      print('VERIFYING DOWNLOADED FILE');
      print('========================================');
      print('Path: $outputPath');
      print('Exists: $exists');

      if (!exists) {
        throw Exception(
          'Downloaded file was not created.',
        );
      }

      final fileSize =
          await file.length();

      print(
        'Size: $fileSize bytes',
      );
      print('========================================');

      if (fileSize <= 0) {
        throw Exception(
          'Downloaded file is empty.',
        );
      }

      // ============================================================
      // SAVE TO PHONE
      // ============================================================

      onProgress(
        0.97,
        'Saving to your phone...',
      );

      if (format == 'mp3') {
        await MediaStoreService.saveAudio(
          filePath: outputPath,
          fileName: '$safeName.mp3',
        );
      } else {
        await MediaStoreService.saveVideo(
          filePath: outputPath,
          fileName: '$safeName.mp4',
        );
      }

      // ============================================================
      // COMPLETE
      // ============================================================

      onProgress(
        1.0,
        'Saved successfully',
      );

      await NotificationService.showCompleted(
        title: media.title,
        format: format.toUpperCase(),
      );

      print('');
      print('========================================');
      print('DOWNLOAD COMPLETE');
      print('========================================');
    } finally {
      // ============================================================
      // CLEANUP TEMPORARY FILE
      // ============================================================

      await _deleteIfExists(
        outputPath,
      );
    }
  }

  // ============================================================
  // GET FORMAT ID
  // ============================================================

  static String _getFormatId(
    dynamic media,
    String format,
  ) {
    if (format == 'mp3') {
      final audio = media.audio;

      if (audio == null) {
        throw Exception(
          'No audio format is available.',
        );
      }

      final id =
          audio.formatId.toString();

      if (id.isEmpty) {
        throw Exception(
          'Audio format ID is empty.',
        );
      }

      return id;
    }

    final video = media.video;

    if (video == null) {
      throw Exception(
        'No video format is available.',
      );
    }

    final id =
        video.formatId.toString();

    if (id.isEmpty) {
      throw Exception(
        'Video format ID is empty.',
      );
    }

    return id;
  }

  // ============================================================
  // DOWNLOAD FINAL FILE
  // ============================================================

  static Future<void> _downloadFinalFile({
    required String url,
    required String path,
    required CancelToken cancelToken,
    required void Function(
      double progress,
    ) onProgress,
  }) async {
    final dio = Dio(
      BaseOptions(
        connectTimeout:
            const Duration(
          seconds: 30,
        ),
        receiveTimeout:
            const Duration(
          minutes: 20,
        ),
        sendTimeout:
            const Duration(
          seconds: 30,
        ),
        headers: {
          'User-Agent':
              'Mozilla/5.0 '
              '(Linux; Android 10) '
              'AppleWebKit/537.36 '
              '(KHTML, like Gecko) '
              'Chrome/140.0 '
              'Mobile Safari/537.36',
          'Accept': '*/*',
        },
      ),
    );

    try {
      await dio.download(
        url,
        path,
        cancelToken: cancelToken,
        deleteOnError: true,
        onReceiveProgress:
            (received, total) {
          if (total <= 0) {
            return;
          }

          final progress =
              (received / total)
                  .clamp(
            0.0,
            1.0,
          );

          onProgress(
            progress,
          );
        },
      );
    } on DioException catch (e) {
      print('');
      print('========================================');
      print('FILE DOWNLOAD ERROR');
      print('========================================');
      print('Type: ${e.type}');
      print(
        'Message: ${e.message}',
      );
      print(
        'Status: ${e.response?.statusCode}',
      );
      print(
        'Response: ${e.response?.data}',
      );
      print('========================================');

      rethrow;
    }
  }

  // ============================================================
  // SAFE FILE NAME
  // ============================================================

  static String _safeFileName(
    String name,
  ) {
    var value = name.trim();

    if (value.isEmpty) {
      value = 'MP34_Download';
    }

    value = value.replaceAll(
      RegExp(
        r'[<>:"/\\|?*\x00-\x1F]',
      ),
      '_',
    );

    if (value.length > 80) {
      value =
          value.substring(0, 80);
    }

    return value;
  }

  // ============================================================
  // DELETE TEMPORARY FILE
  // ============================================================

  static Future<void> _deleteIfExists(
    String path,
  ) async {
    try {
      final file = File(path);

      if (await file.exists()) {
        await file.delete();

        print(
          'Temporary file deleted: $path',
        );
      }
    } catch (e) {
      print(
        'Temporary cleanup failed: $e',
      );
    }
  }
}