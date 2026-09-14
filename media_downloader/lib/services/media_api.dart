import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:media_store_plus/media_store_plus.dart';
import 'package:path_provider/path_provider.dart';

import '../models/analyser.dart';

class MediaApi {
  MediaApi({Dio? client})
      : _client = client ??
            Dio(
              BaseOptions(
                baseUrl: _baseUrl,
                connectTimeout: const Duration(seconds: 20),
                receiveTimeout: const Duration(minutes: 15),
                sendTimeout: const Duration(seconds: 30),
              ),
            );

  static const String _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://mp34-downloader-api.onrender.com',
  );

  final Dio _client;

  // ------------------------------------------------------------
  // ANALYZE
  // ------------------------------------------------------------

  Future<MediaInfo> analyse(String url) async {
    try {
      final response = await _client.post<Map<String, dynamic>>(
        '/analyze',
        data: {
          'url': url,
        },
      );

      return MediaInfo.fromJson(
        response.data ?? <String, dynamic>{},
      );
    } on DioException catch (error) {
      throw MediaApiException(
        _messageFor(error),
      );
    }
  }

  // ------------------------------------------------------------
  // DOWNLOAD
  // ------------------------------------------------------------

  Future<DownloadResult> download(
    String url, {
    required String title,
    CancelToken? cancelToken,
    void Function(int received, int total)? onProgress,
  }) async {
    final notificationId =
        DateTime.now().millisecondsSinceEpoch.remainder(100000);

    File? temporaryFile;

    try {
      await DownloadNotificationService.instance.initialize();

      await DownloadNotificationService.instance.showProgress(
        id: notificationId,
        title: 'Downloading',
        progress: 0,
        indeterminate: true,
        fileName: title,
      );

      // ----------------------------------------------------------
      // Create temporary file inside the application's cache.
      // ----------------------------------------------------------

      final tempDirectory = await getTemporaryDirectory();

      final safeBaseName = _sanitizeFileName(
        title.isEmpty ? 'media_file' : title,
      );

      temporaryFile = File(
        '${tempDirectory.path}/$safeBaseName.download',
      );

      if (await temporaryFile.exists()) {
        await temporaryFile.delete();
      }

      // ----------------------------------------------------------
      // Request the media as a stream.
      // ----------------------------------------------------------

      final response = await _client.post<ResponseBody>(
        '/download',
        data: {
          'url': url,
        },
        cancelToken: cancelToken,
        options: Options(
          responseType: ResponseType.stream,
          headers: {
            'Accept': '*/*',
          },
        ),
      );

      final body = response.data;

      if (body == null) {
        throw const MediaApiException(
          'The server returned an empty response.',
        );
      }

      final total = body.contentLength;

      var received = 0;

      final fileSink = temporaryFile.openWrite();

      try {
        await for (final chunk in body.stream) {
          if (cancelToken?.isCancelled ?? false) {
            throw const DownloadCancelledException();
          }

          fileSink.add(chunk);

          received += chunk.length;

          final progress = total > 0
              ? ((received / total) * 100).round().clamp(0, 100)
              : 0;

          onProgress?.call(
            received,
            total,
          );

          await DownloadNotificationService.instance.showProgress(
            id: notificationId,
            title: 'Downloading',
            progress: progress,
            indeterminate: total <= 0,
            fileName: title,
          );
        }
      } finally {
        await fileSink.close();
      }

      if (!await temporaryFile.exists()) {
        throw const MediaApiException(
          'The downloaded file could not be created.',
        );
      }

      final fileSize = await temporaryFile.length();

      if (fileSize == 0) {
        throw const MediaApiException(
          'The server returned an empty media file.',
        );
      }

      // ----------------------------------------------------------
      // Determine whether this is audio or video.
      // ----------------------------------------------------------

      final extension = _extensionFromTitle(title);

      final isAudio = _isAudioExtension(extension);

      // ----------------------------------------------------------
      // Save into Android shared storage using MediaStore.
      //
      // Video:
      // Movies/MP34 Downloader
      //
      // Audio:
      // Music/MP34 Downloader
      // ----------------------------------------------------------

      await MediaStore.ensureInitialized();

      MediaStore.appFolder = 'MP34 Downloader';

      SaveInfo? savedFile;

      if (isAudio) {
        savedFile = await MediaStore().saveFile(
          tempFilePath: temporaryFile.path,
          dirType: DirType.audio,
          dirName: DirName.music,
          relativePath: 'MP34 Downloader',
        );
      } else {
        savedFile = await MediaStore().saveFile(
          tempFilePath: temporaryFile.path,
          dirType: DirType.video,
          dirName: DirName.movies,
          relativePath: 'MP34 Downloader',
        );
      }

      if (savedFile == null || !savedFile.isSuccessful) {
        throw const MediaApiException(
          'The file was downloaded but could not be saved to phone storage.',
        );
      }

      // media_store_plus removes the temporary file after saving.
      temporaryFile = null;

      // ----------------------------------------------------------
      // Complete notification.
      // ----------------------------------------------------------

      await DownloadNotificationService.instance.showComplete(
        id: notificationId,
        fileName: _displayFileName(title, extension),
      );

      return DownloadResult(
        fileName: _displayFileName(
          title,
          extension,
        ),
        location: isAudio
            ? 'Music/MP34 Downloader'
            : 'Movies/MP34 Downloader',
      );
    } on DioException catch (error) {
      if (error.type == DioExceptionType.cancel) {
        await DownloadNotificationService.instance.showCancelled(
          id: notificationId,
        );

        throw const DownloadCancelledException();
      }

      await DownloadNotificationService.instance.showFailed(
        id: notificationId,
      );

      throw MediaApiException(
        _messageFor(error),
      );
    } on DownloadCancelledException {
      await DownloadNotificationService.instance.showCancelled(
        id: notificationId,
      );

      rethrow;
    } on MediaApiException {
      await DownloadNotificationService.instance.showFailed(
        id: notificationId,
      );

      rethrow;
    } catch (error) {
      await DownloadNotificationService.instance.showFailed(
        id: notificationId,
      );

      throw MediaApiException(
        'Download failed: $error',
      );
    } finally {
      if (temporaryFile != null) {
        try {
          if (await temporaryFile.exists()) {
            await temporaryFile.delete();
          }
        } catch (_) {}
      }
    }
  }

  // ------------------------------------------------------------
  // HELPERS
  // ------------------------------------------------------------

  String _extensionFromTitle(String title) {
    final cleanTitle = title.trim();

    final dotIndex = cleanTitle.lastIndexOf('.');

    if (dotIndex == -1 || dotIndex == cleanTitle.length - 1) {
      return '';
    }

    return cleanTitle.substring(dotIndex + 1).toLowerCase();
  }

  bool _isAudioExtension(String extension) {
    const audioExtensions = {
      'mp3',
      'm4a',
      'aac',
      'wav',
      'flac',
      'ogg',
      'opus',
    };

    return audioExtensions.contains(extension);
  }

  String _displayFileName(
    String title,
    String extension,
  ) {
    final cleaned = _sanitizeFileName(title);

    if (extension.isEmpty) {
      return cleaned;
    }

    if (cleaned.toLowerCase().endsWith(
          '.$extension',
        )) {
      return cleaned;
    }

    return '$cleaned.$extension';
  }

  String _sanitizeFileName(String fileName) {
    var cleaned = fileName.replaceAll(
      RegExp(r'[<>:"/\\|?*\x00-\x1F]'),
      '_',
    );

    cleaned = cleaned.trim();

    if (cleaned.isEmpty) {
      return 'media_file';
    }

    // Keep names reasonable for Android filesystems.
    if (cleaned.length > 180) {
      cleaned = cleaned.substring(0, 180);
    }

    return cleaned;
  }

  String _messageFor(DioException error) {
    final data = error.response?.data;

    if (data is Map && data['detail'] is String) {
      return data['detail'] as String;
    }

    if (error.type == DioExceptionType.connectionTimeout) {
      return 'Connection timed out. Please try again.';
    }

    if (error.type == DioExceptionType.sendTimeout) {
      return 'The request took too long to send.';
    }

    if (error.type == DioExceptionType.receiveTimeout) {
      return 'The download took too long. Please try again.';
    }

    if (error.type == DioExceptionType.connectionError) {
      return 'Could not connect to the download server.';
    }

    if (error.response?.statusCode == 404) {
      return 'Download endpoint was not found.';
    }

    if (error.response?.statusCode == 422) {
      return 'The server could not process this media link.';
    }

    if (error.response?.statusCode == 500) {
      return 'The server encountered an error while downloading.';
    }

    return 'Something went wrong while processing the media.';
  }
}

// ============================================================
// DOWNLOAD RESULT
// ============================================================

class DownloadResult {
  const DownloadResult({
    required this.fileName,
    required this.location,
  });

  final String fileName;
  final String location;
}

// ============================================================
// API EXCEPTION
// ============================================================

class MediaApiException implements Exception {
  const MediaApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

// ============================================================
// DOWNLOAD CANCELLED
// ============================================================

class DownloadCancelledException implements Exception {
  const DownloadCancelledException();

  @override
  String toString() => 'Download cancelled';
}

// ============================================================
// NOTIFICATION SERVICE
// ============================================================

class DownloadNotificationService {
  DownloadNotificationService._();

  static final DownloadNotificationService instance =
      DownloadNotificationService._();

  final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();

  bool _initialized = false;

  static const AndroidNotificationChannel _channel =
      AndroidNotificationChannel(
    'downloads',
    'Downloads',
    description: 'Media download progress and completion',
    importance: Importance.low,
  );

  Future<void> initialize() async {
    if (_initialized) {
      return;
    }

    const androidSettings = AndroidInitializationSettings(
      '@mipmap/ic_launcher',
    );

    const settings = InitializationSettings(
      android: androidSettings,
    );

    await _notifications.initialize(settings: settings);

    final androidImplementation =
        _notifications.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();

    await androidImplementation?.createNotificationChannel(
      _channel,
    );

    await androidImplementation?.requestNotificationsPermission();

    _initialized = true;
  }

  Future<void> _showNotification({
    required int id,
    required String title,
    required String body,
    required NotificationDetails notificationDetails,
  }) async {
    await _notifications.show(
      id: id,
      title: title,
      body: body,
      notificationDetails: notificationDetails,
    );
  }

  Future<void> showProgress({
    required int id,
    required String title,
    required int progress,
    required bool indeterminate,
    required String fileName,
  }) async {
    await initialize();

    final details = AndroidNotificationDetails(
      _channel.id,
      _channel.name,
      channelDescription: _channel.description,
      importance: Importance.low,
      priority: Priority.low,
      ongoing: true,
      autoCancel: false,
      onlyAlertOnce: true,
      showProgress: true,
      maxProgress: 100,
      progress: progress.clamp(0, 100),
      indeterminate: indeterminate,
      icon: '@mipmap/ic_launcher',
      styleInformation: BigTextStyleInformation(
        '$fileName\nDownloading media...',
      ),
    );

    await _showNotification(
      id: id,
      title: title,
      body: indeterminate
          ? 'Preparing download...'
          : '$progress% downloaded',
      notificationDetails: NotificationDetails(
        android: details,
      ),
    );
  }

  Future<void> showComplete({
    required int id,
    required String fileName,
  }) async {
    await initialize();

    const details = AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription: 'Media download progress and completion',
      importance: Importance.high,
      priority: Priority.high,
      autoCancel: true,
      ongoing: false,
      icon: '@mipmap/ic_launcher',
    );

    await _showNotification(
      id: id,
      title: 'Download complete',
      body: fileName,
      notificationDetails: const NotificationDetails(
        android: details,
      ),
    );
  }

  Future<void> showCancelled({
    required int id,
  }) async {
    await initialize();

    const details = AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription: 'Media download progress and completion',
      importance: Importance.low,
      priority: Priority.low,
      autoCancel: true,
      ongoing: false,
      icon: '@mipmap/ic_launcher',
    );

    await _showNotification(
      id: id,
      title: 'Download cancelled',
      body: 'The download was cancelled.',
      notificationDetails: const NotificationDetails(
        android: details,
      ),
    );
  }

  Future<void> showFailed({
    required int id,
  }) async {
    await initialize();

    const details = AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription: 'Media download progress and completion',
      importance: Importance.high,
      priority: Priority.high,
      autoCancel: true,
      ongoing: false,
      icon: '@mipmap/ic_launcher',
    );

    await _showNotification(
      id: id,
      title: 'Download failed',
      body: 'Something went wrong while downloading the media.',
      notificationDetails: const NotificationDetails(
        android: details,
      ),
    );
  }
}