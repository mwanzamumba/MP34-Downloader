import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:media_store_plus/media_store_plus.dart';
import 'package:path_provider/path_provider.dart';

import '../models/analyser.dart';

class MediaApi {
  MediaApi._();

  static final MediaApi instance = MediaApi._();

  static const String baseUrl =
      'https://mp34-downloader-api.onrender.com';

  final Dio _dio = Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(minutes: 30),
      sendTimeout: const Duration(seconds: 30),
    ),
  );

  final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();

  // ============================================================
  // NOTIFICATIONS
  // ============================================================

  Future<void> initializeNotifications() async {
    const androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');

    const settings = InitializationSettings(
      android: androidSettings,
    );

    await _notifications.initialize(settings: settings);

    final androidPlugin = _notifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();

    await androidPlugin?.requestNotificationsPermission();
  }

  // ============================================================
  // ANALYZE URL
  // ============================================================

  Future<MediaInfo> analyze(String url) async {
    try {
      final response = await _dio.post(
        '/analyze',
        data: {
          'url': url.trim(),
        },
      );

      final data = Map<String, dynamic>.from(response.data);

      return MediaInfo.fromJson(data);
    } on DioException catch (error) {
      String message = 'Could not analyse the link.';

      if (error.response?.data is Map) {
        final responseData =
            Map<String, dynamic>.from(error.response!.data);

        final detail = responseData['detail'];

        if (detail != null) {
          message = detail.toString();
        }
      } else if (error.message != null) {
        message = error.message!;
      }

      throw MediaApiException(message);
    }
  }

  // ============================================================
  // DOWNLOAD
  // ============================================================

  Future<String> download(
    MediaInfo media, {
    required void Function(double progress) onProgress,
    CancelToken? cancelToken,
  }) async {
    await initializeNotifications();

    final directory = await getTemporaryDirectory();

    final safeTitle = _safeFileName(media.title);

    final tempFile = File(
      '${directory.path}/$safeTitle.download',
    );

    try {
      // --------------------------------------------------------
      // START
      // --------------------------------------------------------

      onProgress(0.0);

      await _showNotification(
        id: 1001,
        title: 'Preparing download',
        body: media.title,
        progress: 0,
      );

      // --------------------------------------------------------
      // REQUEST FILE FROM SERVER
      // --------------------------------------------------------

      final response = await _dio.post<ResponseBody>(
        '/download',
        data: {
          'url': media.sourceUrl,
        },
        options: Options(
          responseType: ResponseType.stream,
          followRedirects: true,
          receiveTimeout: const Duration(minutes: 30),
        ),
        cancelToken: cancelToken,

        onReceiveProgress: (received, total) {
          if (total <= 0) {
            return;
          }

          final actualProgress = received / total;

          // Do not show 100% yet.
          //
          // 100% should only appear AFTER:
          // 1. The file is written.
          // 2. MediaStore saves it.
          final displayProgress =
              actualProgress >= 1.0 ? 0.99 : actualProgress;

          onProgress(displayProgress);

          _showNotification(
            id: 1001,
            title: 'Downloading',
            body:
                '${(displayProgress * 100).toStringAsFixed(0)}% • ${media.title}',
            progress:
                (displayProgress * 100).round(),
          );
        },
      );

      final responseBody = response.data;

      if (responseBody == null) {
        throw MediaApiException(
          'The server returned an empty file.',
        );
      }

      // --------------------------------------------------------
      // WRITE SERVER RESPONSE TO TEMP FILE
      // --------------------------------------------------------

      await _showNotification(
        id: 1001,
        title: 'Downloading',
        body: 'Receiving ${media.title}...',
        progress: 99,
      );

      final sink = tempFile.openWrite();

      try {
        await for (final chunk in responseBody.stream) {
          sink.add(chunk);
        }
      } finally {
        await sink.flush();
        await sink.close();
      }

      // --------------------------------------------------------
      // CHECK TEMP FILE
      // --------------------------------------------------------

      if (!await tempFile.exists()) {
        throw MediaApiException(
          'The downloaded file was not created.',
        );
      }

      final fileSize = await tempFile.length();

      if (fileSize <= 0) {
        throw MediaApiException(
          'The downloaded file is empty.',
        );
      }

      // --------------------------------------------------------
      // DOWNLOAD FINISHED
      //
      // But we intentionally DON'T show 100% yet.
      // --------------------------------------------------------

      onProgress(0.995);

      await _showNotification(
        id: 1001,
        title: 'Saving',
        body: 'Saving ${media.title} to your device...',
        progress: 99,
      );

      // --------------------------------------------------------
      // SAVE TO ANDROID MEDIA LIBRARY
      // --------------------------------------------------------

      final savedPath = await _saveToMediaStore(
        tempFile,
        media,
      );

      // --------------------------------------------------------
      // DELETE TEMPORARY FILE
      // --------------------------------------------------------

      try {
        await tempFile.delete();
      } catch (_) {
        // Not critical if deletion fails.
      }

      // --------------------------------------------------------
      // NOW IT IS REALLY COMPLETE
      // --------------------------------------------------------

      onProgress(1.0);

      await _showCompletedNotification(
        title: 'Download complete',
        body: '${media.title} saved to your device',
      );

      return savedPath;
    } on DioException catch (error) {
      // --------------------------------------------------------
      // CANCELLED
      // --------------------------------------------------------

      if (CancelToken.isCancel(error)) {
        await _showNotification(
          id: 1001,
          title: 'Download cancelled',
          body: media.title,
          progress: 0,
        );

        throw DownloadCancelledException();
      }

      // --------------------------------------------------------
      // DIO ERROR
      // --------------------------------------------------------

      String message = 'Download failed.';

      if (error.response?.data is Map) {
        final data =
            Map<String, dynamic>.from(
          error.response!.data,
        );

        final detail = data['detail'];

        if (detail != null) {
          message = detail.toString();
        }
      } else if (error.message != null) {
        message = error.message!;
      }

      await _showNotification(
        id: 1001,
        title: 'Download failed',
        body: message,
        progress: 0,
      );

      throw MediaApiException(message);
    } catch (error) {
      // --------------------------------------------------------
      // OTHER ERROR
      // --------------------------------------------------------

      await _showNotification(
        id: 1001,
        title: 'Download failed',
        body: error.toString(),
        progress: 0,
      );

      if (error is MediaApiException) {
        rethrow;
      }

      throw MediaApiException(
        'Could not save the downloaded file: $error',
      );
    }
  }

  // ============================================================
  // SAVE TO MEDIASTORE
  // ============================================================

  Future<String> _saveToMediaStore(
    File file,
    MediaInfo media,
  ) async {
    final mediaStore = MediaStore();

    final extension = _getExtension(
      media.title,
      file.path,
    );

    final isAudio = _isAudioExtension(extension);

    final fileName =
        '${_safeFileName(media.title)}.$extension';

    SaveInfo? result;

    try {
      if (isAudio) {
        // ------------------------------------------------------
        // AUDIO → MUSIC
        // ------------------------------------------------------

        result = await mediaStore.saveFile(
          tempFilePath: file.path,
          dirType: DirType.audio,
          dirName: DirName.music,
          relativePath: 'MP34 Downloader',
        );
      } else {
        // ------------------------------------------------------
        // VIDEO → MOVIES
        // ------------------------------------------------------

        result = await mediaStore.saveFile(
          tempFilePath: file.path,
          dirType: DirType.video,
          dirName: DirName.movies,
          relativePath: 'MP34 Downloader',
        );
      }
    } catch (error) {
      throw MediaApiException(
        'MediaStore error: $error',
      );
    }

    if (result == null) {
      throw MediaApiException(
        'MediaStore returned no result.',
      );
    }

    if (!result.isSuccessful) {
      throw MediaApiException(
        'Android could not save the file to your media library.',
      );
    }

    return fileName;
  }

  // ============================================================
  // DOWNLOAD NOTIFICATION
  // ============================================================

  Future<void> _showNotification({
    required int id,
    required String title,
    required String body,
    required int progress,
  }) async {
    final androidDetails =
        AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription:
          'Media download progress',
      importance: Importance.low,
      priority: Priority.low,
      onlyAlertOnce: true,
      showProgress: true,
      maxProgress: 100,
      progress: progress,
    );

    final details = NotificationDetails(
      android: androidDetails,
    );

    await _notifications.show(
      id: id,
      title: title,
      body: body,
      notificationDetails: details,
    );
  }

  // ============================================================
  // COMPLETED NOTIFICATION
  // ============================================================

  Future<void> _showCompletedNotification({
    required String title,
    required String body,
  }) async {
    const androidDetails =
        AndroidNotificationDetails(
      'downloads_complete',
      'Completed downloads',
      channelDescription:
          'Completed media downloads',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    );

    const details = NotificationDetails(
      android: androidDetails,
    );

    await _notifications.show(
      id: 1001,
      title: title,
      body: body,
      notificationDetails: details,
    );
  }

  // ============================================================
  // FILE EXTENSION
  // ============================================================

  String _getExtension(
    String title,
    String path,
  ) {
    final pathExtension =
        path.split('.').last.toLowerCase();

    const knownExtensions = {
      'mp4',
      'mkv',
      'webm',
      'mov',
      'avi',
      'mp3',
      'm4a',
      'aac',
      'wav',
      'ogg',
      'flac',
    };

    if (knownExtensions.contains(pathExtension)) {
      return pathExtension;
    }

    return 'mp4';
  }

  // ============================================================
  // AUDIO CHECK
  // ============================================================

  bool _isAudioExtension(
    String extension,
  ) {
    return {
      'mp3',
      'm4a',
      'aac',
      'wav',
      'ogg',
      'flac',
    }.contains(
      extension.toLowerCase(),
    );
  }

  // ============================================================
  // MIME TYPE
  // ============================================================

  String _mimeType(
    String extension,
  ) {
    switch (extension.toLowerCase()) {
      case 'mp3':
        return 'audio/mpeg';

      case 'm4a':
        return 'audio/mp4';

      case 'aac':
        return 'audio/aac';

      case 'wav':
        return 'audio/wav';

      case 'ogg':
        return 'audio/ogg';

      case 'flac':
        return 'audio/flac';

      case 'webm':
        return 'video/webm';

      case 'mkv':
        return 'video/x-matroska';

      case 'mov':
        return 'video/quicktime';

      case 'avi':
        return 'video/x-msvideo';

      case 'mp4':
      default:
        return 'video/mp4';
    }
  }

  // ============================================================
  // SAFE FILE NAME
  // ============================================================

  String _safeFileName(
    String value,
  ) {
    var result = value.trim();

    if (result.isEmpty) {
      result = 'media';
    }

    result = result.replaceAll(
      RegExp(r'[<>:"/\\|?*]'),
      '_',
    );

    result = result.replaceAll(
      RegExp(r'\s+'),
      ' ',
    );

    if (result.length > 100) {
      result = result.substring(0, 100);
    }

    return result;
  }
}

// ================================================================
// EXCEPTIONS
// ================================================================

class MediaApiException
    implements Exception {
  final String message;

  MediaApiException(this.message);

  @override
  String toString() => message;
}

class DownloadCancelledException
    implements Exception {
  @override
  String toString() =>
      'Download cancelled.';
}