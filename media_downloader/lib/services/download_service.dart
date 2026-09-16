import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';

import '../models/analyser.dart';
import 'media_processor.dart';
import 'media_store_service.dart';
import 'notification_service.dart';

class DownloadService {
  static Future<void> download({
    required dynamic media,
    required String format,
    required CancelToken cancelToken,
    required void Function(double progress, String status) onProgress,
  }) async {
    final tempDirectory = await getTemporaryDirectory();

    final safeName = _safeFileName(media.title);

    // Give every download a unique temporary filename.
    final timestamp = DateTime.now().millisecondsSinceEpoch;

    final videoPath =
        '${tempDirectory.path}/${safeName}_$timestamp.video.mp4';

    final audioPath =
        '${tempDirectory.path}/${safeName}_$timestamp.audio.m4a';

    final outputPath = format == 'mp4'
        ? '${tempDirectory.path}/${safeName}_$timestamp.mp4'
        : '${tempDirectory.path}/${safeName}_$timestamp.mp3';

    try {
      await NotificationService.showStarted(
        title: media.title,
        format: format.toUpperCase(),
      );

      if (format == 'mp3') {
        await _downloadMp3(
          media: media,
          audioPath: audioPath,
          outputPath: outputPath,
          cancelToken: cancelToken,
          onProgress: onProgress,
        );
      } else {
        await _downloadMp4(
          media: media,
          videoPath: videoPath,
          audioPath: audioPath,
          outputPath: outputPath,
          cancelToken: cancelToken,
          onProgress: onProgress,
        );
      }

      if (cancelToken.isCancelled) {
        throw DioException(
          requestOptions: RequestOptions(path: ''),
          type: DioExceptionType.cancel,
        );
      }

      onProgress(
        0.97,
        'Saving to your phone...',
      );

      print('');
      print('========================================');
      print('FINAL SAVE');
      print('========================================');
      print('Format: $format');
      print('Temporary output: $outputPath');
      print('File exists: ${await File(outputPath).exists()}');
      print('File size: ${await File(outputPath).length()} bytes');
      print('========================================');

      if (format == 'mp4') {
        await MediaStoreService.saveVideo(
          filePath: outputPath,

          // The timestamp is removed from the final visible name.
          fileName: '$safeName.mp4',
        );
      } else {
        await MediaStoreService.saveAudio(
          filePath: outputPath,
          fileName: '$safeName.mp3',
        );
      }

      onProgress(
        1.0,
        'Saved successfully',
      );

      await NotificationService.showCompleted(
        title: media.title,
        format: format.toUpperCase(),
      );
    } finally {
      await _deleteIfExists(videoPath);
      await _deleteIfExists(audioPath);
      await _deleteIfExists(outputPath);
    }
  }

  // ============================================================
  // MP4
  // ============================================================

  static Future<void> _downloadMp4({
    required dynamic media,
    required String videoPath,
    required String audioPath,
    required String outputPath,
    required CancelToken cancelToken,
    required void Function(double progress, String status) onProgress,
  }) async {
    onProgress(
      0.01,
      'Downloading video and audio...',
    );

    double videoProgress = 0;
    double audioProgress = 0;

    final videoFuture = _downloadStream(
      url: media.video.url,
      path: videoPath,
      cancelToken: cancelToken,
      onProgress: (value) {
        videoProgress = value;

        final combined =
            (videoProgress * 0.70) +
            (audioProgress * 0.20);

        onProgress(
          combined,
          'Downloading video... '
          '${(videoProgress * 100).round()}%',
        );
      },
    );

    final audioFuture = _downloadStream(
      url: media.audio.url,
      path: audioPath,
      cancelToken: cancelToken,
      onProgress: (value) {
        audioProgress = value;

        final combined =
            (videoProgress * 0.70) +
            (audioProgress * 0.20);

        onProgress(
          combined,
          'Downloading audio... '
          '${(audioProgress * 100).round()}%',
        );
      },
    );

    await Future.wait([
      videoFuture,
      audioFuture,
    ]);

    if (cancelToken.isCancelled) {
      throw DioException(
        requestOptions: RequestOptions(path: ''),
        type: DioExceptionType.cancel,
      );
    }

    onProgress(
      0.91,
      'Combining video and audio...',
    );

    await MediaProcessor.mergeToMp4(
      videoPath: videoPath,
      audioPath: audioPath,
      outputPath: outputPath,
    );

    onProgress(
      0.96,
      'Preparing final MP4...',
    );
  }

  // ============================================================
  // MP3
  // ============================================================

  static Future<void> _downloadMp3({
    required dynamic media,
    required String audioPath,
    required String outputPath,
    required CancelToken cancelToken,
    required void Function(double progress, String status) onProgress,
  }) async {
    onProgress(
      0.01,
      'Downloading audio...',
    );

    await _downloadStream(
      url: media.audio.url,
      path: audioPath,
      cancelToken: cancelToken,
      onProgress: (value) {
        onProgress(
          value * 0.80,
          'Downloading audio... '
          '${(value * 100).round()}%',
        );
      },
    );

    if (cancelToken.isCancelled) {
      throw DioException(
        requestOptions: RequestOptions(path: ''),
        type: DioExceptionType.cancel,
      );
    }

    onProgress(
      0.88,
      'Converting to MP3...',
    );

    await MediaProcessor.convertToMp3(
      audioPath: audioPath,
      outputPath: outputPath,
    );

    onProgress(
      0.96,
      'Preparing final MP3...',
    );
  }

  // ============================================================
  // STREAM DOWNLOAD
  // ============================================================

  static Future<void> _downloadStream({
    required String url,
    required String path,
    required CancelToken cancelToken,
    required void Function(double progress) onProgress,
  }) async {
    final dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(minutes: 10),
        sendTimeout: const Duration(seconds: 30),
        headers: {
          'User-Agent':
              'Mozilla/5.0 (Linux; Android 10) '
              'AppleWebKit/537.36 '
              '(KHTML, like Gecko) '
              'Chrome/140.0 Mobile Safari/537.36',
          'Accept': '*/*',
        },
      ),
    );

    await dio.download(
      url,
      path,
      cancelToken: cancelToken,
      deleteOnError: true,
      onReceiveProgress: (received, total) {
        if (total <= 0) {
          return;
        }

        onProgress(
          (received / total).clamp(0.0, 1.0),
        );
      },
    );
  }

  // ============================================================
  // SAFE FILE NAME
  // ============================================================

  static String _safeFileName(String name) {
    var value = name.trim();

    if (value.isEmpty) {
      value = 'MP34_Download';
    }

    value = value.replaceAll(
      RegExp(r'[<>:"/\\|?*\x00-\x1F]'),
      '_',
    );

    if (value.length > 80) {
      value = value.substring(0, 80);
    }

    return value;
  }

  // ============================================================
  // CLEANUP
  // ============================================================

  static Future<void> _deleteIfExists(String path) async {
    try {
      final file = File(path);

      if (await file.exists()) {
        await file.delete();
      }
    } catch (_) {
      // Temporary cleanup should never crash the download.
    }
  }
}