import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:media_store_plus/media_store_plus.dart';
import 'package:path_provider/path_provider.dart';

import '../models/analyser.dart';

class MediaApi {
  static const String _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://mp34-downloader-api.onrender.com',
  );

  final Dio _dio = Dio(
    BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(minutes: 30),
      sendTimeout: const Duration(seconds: 30),
    ),
  );

  final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();

  bool _notificationsInitialized = false;

  // ============================================================
  // NOTIFICATIONS
  // ============================================================

  Future<void> initializeNotifications() async {
    if (_notificationsInitialized) {
      return;
    }

    const androidSettings = AndroidInitializationSettings(
      '@mipmap/ic_launcher',
    );

    const settings = InitializationSettings(
      android: androidSettings,
    );

    await _notifications.initialize(settings: settings);

    final androidPlugin =
        _notifications.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();

    await androidPlugin?.requestNotificationsPermission();

    const channel = AndroidNotificationChannel(
      'downloads',
      'Downloads',
      description: 'MP34 Downloader download notifications',
      importance: Importance.low,
    );

    await androidPlugin?.createNotificationChannel(channel);

    _notificationsInitialized = true;
  }

  // ============================================================
  // ANALYZE
  // ============================================================

  Future<MediaInfo> analyse(String url) async {
    try {
      final response = await _dio.post(
        '/analyze',
        data: {
          'url': url.trim(),
        },
      );

      if (response.statusCode != 200) {
        throw MediaApiException(
          'Analysis failed with status ${response.statusCode}.',
        );
      }

      if (response.data is! Map) {
        throw const MediaApiException(
          'The server returned an invalid response.',
        );
      }

      return MediaInfo.fromJson(
        Map<String, dynamic>.from(
          response.data as Map,
        ),
      );
    } on DioException catch (error) {
      throw MediaApiException(
        _messageFor(error),
      );
    }
  }

  // ============================================================
  // DOWNLOAD
  // ============================================================

  Future<DownloadResult> download(
    MediaInfo media, {
    required CancelToken cancelToken,
    void Function(int received, int total)? onProgress,
  }) async {
    await initializeNotifications();

    final directory = await getTemporaryDirectory();

    final safeTitle = _sanitizeFileName(media.title);

    final extension = media.extension.trim().isEmpty
        ? 'mp4'
        : media.extension.trim().replaceAll('.', '');

    final fileName = '$safeTitle.$extension';

    final partialFile = File(
      '${directory.path}/$fileName.part',
    );

    int existingBytes = 0;

    if (await partialFile.exists()) {
      existingBytes = await partialFile.length();
    }

    // ----------------------------------------------------------
    // FIRST ATTEMPT
    // ----------------------------------------------------------

    try {
      return await _downloadFromUrl(
        media: media,
        downloadUrl: media.downloadUrl,
        partialFile: partialFile,
        fileName: fileName,
        existingBytes: existingBytes,
        cancelToken: cancelToken,
        onProgress: onProgress,
      );
    } on DownloadPausedException {
      rethrow;
    } on DownloadCancelledException {
      rethrow;
    } on DioException catch (error) {
      // --------------------------------------------------------
      // EXPIRED DIRECT URL
      // --------------------------------------------------------
      //
      // 403 / 404 / 416 can mean that the temporary direct URL
      // returned by yt-dlp has expired.
      //
      // Re-analyze the ORIGINAL URL to get a fresh direct URL.
      // --------------------------------------------------------

      if (_isExpiredUrlError(error)) {
        return await _refreshAndRetry(
          media: media,
          partialFile: partialFile,
          fileName: fileName,
          existingBytes: existingBytes,
          cancelToken: cancelToken,
          onProgress: onProgress,
        );
      }

      throw MediaApiException(
        _messageFor(error),
      );
    }
  }

  // ============================================================
  // REFRESH EXPIRED URL
  // ============================================================

  Future<DownloadResult> _refreshAndRetry({
    required MediaInfo media,
    required File partialFile,
    required String fileName,
    required int existingBytes,
    required CancelToken cancelToken,
    void Function(int received, int total)? onProgress,
  }) async {
    // If the user paused/cancelled while we were handling the
    // expired URL, don't perform another network request.
    if (cancelToken.isCancelled) {
      final reason =
          cancelToken.cancelError?.message ?? '';

      if (reason == 'cancel') {
        throw const DownloadCancelledException();
      }

      throw const DownloadPausedException();
    }

    await showRefreshing(fileName);

    MediaInfo freshMedia;

    try {
      // IMPORTANT:
      // We use the original URL, NOT the old temporary
      // download URL.
      freshMedia = await analyse(
        media.sourceUrl,
      );
    } catch (error) {
      throw MediaApiException(
        'The media link has expired and could not be refreshed: $error',
      );
    }

    if (freshMedia.downloadUrl.isEmpty) {
      throw const MediaApiException(
        'The server could not generate a new download URL.',
      );
    }

    // Re-check partial file size because something could have
    // changed while refreshing the URL.
    int currentBytes = 0;

    if (await partialFile.exists()) {
      currentBytes = await partialFile.length();
    }

    try {
      return await _downloadFromUrl(
        media: freshMedia,
        downloadUrl: freshMedia.downloadUrl,
        partialFile: partialFile,
        fileName: fileName,
        existingBytes: currentBytes,
        cancelToken: cancelToken,
        onProgress: onProgress,
      );
    } on DownloadPausedException {
      rethrow;
    } on DownloadCancelledException {
      rethrow;
    } on DioException catch (error) {
      throw MediaApiException(
        _messageFor(error),
      );
    }
  }

  // ============================================================
  // DOWNLOAD FROM DIRECT URL
  // ============================================================

  Future<DownloadResult> _downloadFromUrl({
    required MediaInfo media,
    required String downloadUrl,
    required File partialFile,
    required String fileName,
    required int existingBytes,
    required CancelToken cancelToken,
    void Function(int received, int total)? onProgress,
  }) async {
    if (downloadUrl.isEmpty) {
      throw const MediaApiException(
        'No downloadable media URL was provided.',
      );
    }

    final headers = <String, dynamic>{
      'Accept': '*/*',
    };

    // ----------------------------------------------------------
    // REQUEST REMAINING BYTES
    // ----------------------------------------------------------

    if (existingBytes > 0) {
      headers['Range'] = 'bytes=$existingBytes-';
    }

    Response<ResponseBody> response;

    try {
      response = await _dio.get<ResponseBody>(
        downloadUrl,
        cancelToken: cancelToken,
        options: Options(
          responseType: ResponseType.stream,
          followRedirects: true,
          maxRedirects: 10,
          headers: headers,
          validateStatus: (status) {
            return status != null &&
                status >= 200 &&
                status < 400;
          },
        ),
      );
    } on DioException catch (error) {
      if (error.type == DioExceptionType.cancel) {
        _throwCancellation(
          cancelToken,
        );
      }

      rethrow;
    }

    final statusCode = response.statusCode ?? 0;

    // ----------------------------------------------------------
    // RANGE RESPONSE
    // ----------------------------------------------------------
    //
    // 206 = server accepted our Range request.
    //
    // If we already have 300 MB and receive 206, we append the
    // new bytes to the existing 300 MB.
    //
    // ----------------------------------------------------------

    if (existingBytes > 0 && statusCode == 206) {
      return await _writeResponse(
        response: response,
        media: media,
        partialFile: partialFile,
        fileName: fileName,
        existingBytes: existingBytes,
        cancelToken: cancelToken,
        onProgress: onProgress,
      );
    }

    // ----------------------------------------------------------
    // SERVER DOES NOT SUPPORT RANGE
    // ----------------------------------------------------------
    //
    // If we requested Range but server returned 200, it means
    // the server ignored the Range request.
    //
    // We MUST NOT append a complete file to our partial file.
    // Start from zero.
    // ----------------------------------------------------------

    if (existingBytes > 0 && statusCode == 200) {
      if (await partialFile.exists()) {
        await partialFile.delete();
      }

      return await _writeResponse(
        response: response,
        media: media,
        partialFile: partialFile,
        fileName: fileName,
        existingBytes: 0,
        cancelToken: cancelToken,
        onProgress: onProgress,
      );
    }

    // ----------------------------------------------------------
    // NORMAL NEW DOWNLOAD
    // ----------------------------------------------------------

    if (statusCode >= 200 && statusCode < 300) {
      return await _writeResponse(
        response: response,
        media: media,
        partialFile: partialFile,
        fileName: fileName,
        existingBytes: 0,
        cancelToken: cancelToken,
        onProgress: onProgress,
      );
    }

    throw DioException(
      requestOptions: RequestOptions(
        path: downloadUrl,
      ),
      response: response,
      message: 'Media server returned HTTP $statusCode.',
    );
  }

  // ============================================================
  // WRITE RESPONSE
  // ============================================================

  Future<DownloadResult> _writeResponse({
    required Response<ResponseBody> response,
    required MediaInfo media,
    required File partialFile,
    required String fileName,
    required int existingBytes,
    required CancelToken cancelToken,
    void Function(int received, int total)? onProgress,
  }) async {
    final body = response.data;

    if (body == null) {
      throw const MediaApiException(
        'The media server returned an empty response.',
      );
    }

    final responseLength = body.contentLength;

    int totalBytes = -1;

    if (responseLength >= 0) {
      totalBytes = existingBytes + responseLength;
    }

    final sink = partialFile.openWrite(
      mode: existingBytes > 0
          ? FileMode.append
          : FileMode.write,
    );

    int receivedBytes = existingBytes;

    try {
      await showProgress(
        fileName,
        receivedBytes,
        totalBytes,
      );

      await for (final chunk in body.stream) {
        // ------------------------------------------------------
        // CHECK PAUSE/CANCEL
        // ------------------------------------------------------

        if (cancelToken.isCancelled) {
          _throwCancellation(
            cancelToken,
          );
        }

        sink.add(chunk);

        receivedBytes += chunk.length;

        onProgress?.call(
          receivedBytes,
          totalBytes,
        );

        await showProgress(
          fileName,
          receivedBytes,
          totalBytes,
        );
      }

      await sink.flush();
      await sink.close();

      // --------------------------------------------------------
      // VERIFY
      // --------------------------------------------------------

      if (!await partialFile.exists()) {
        throw const MediaApiException(
          'Downloaded file was not created.',
        );
      }

      final fileSize = await partialFile.length();

      if (fileSize <= 0) {
        throw const MediaApiException(
          'Downloaded file is empty.',
        );
      }

      // --------------------------------------------------------
      // SAVE TO MEDIASTORE
      // --------------------------------------------------------

      final saveInfo = await _saveToMediaStore(
        partialFile,
        media,
      );

      if (saveInfo == null ||
          !saveInfo.isSuccessful) {
        throw const MediaApiException(
          'Could not save the file to your phone.',
        );
      }

      // --------------------------------------------------------
      // REMOVE TEMPORARY .PART FILE
      // --------------------------------------------------------

      if (await partialFile.exists()) {
        await partialFile.delete();
      }

      await showComplete(fileName);

      return DownloadResult(
        fileName: fileName,
        location: _downloadLocation(media),
      );
    } catch (error) {
      // --------------------------------------------------------
      // IMPORTANT:
      //
      // DO NOT DELETE THE .part FILE HERE.
      //
      // Pause needs it for Resume.
      // Cancel will delete it separately.
      // --------------------------------------------------------

      try {
        await sink.flush();
      } catch (_) {}

      try {
        await sink.close();
      } catch (_) {}

      rethrow;
    }
  }

  // ============================================================
  // SAVE TO ANDROID MEDIASTORE
  // ============================================================

  Future<SaveInfo?> _saveToMediaStore(
    File file,
    MediaInfo media,
  ) async {
    final extension =
        media.extension.toLowerCase();

    final isAudio = [
      'mp3',
      'm4a',
      'aac',
      'wav',
      'ogg',
      'opus',
      'flac',
    ].contains(extension);

    if (isAudio) {
      return MediaStore().saveFile(
        tempFilePath: file.path,
        dirType: DirType.audio,
        dirName: DirName.music,
        relativePath: 'MP34 Downloader',
      );
    }

    return MediaStore().saveFile(
      tempFilePath: file.path,
      dirType: DirType.video,
      dirName: DirName.movies,
      relativePath: 'MP34 Downloader',
    );
  }

  // ============================================================
  // DELETE PARTIAL DOWNLOAD
  // ============================================================

  Future<void> deletePartialDownload(
    MediaInfo media,
  ) async {
    final directory =
        await getTemporaryDirectory();

    final safeTitle =
        _sanitizeFileName(media.title);

    final extension =
        media.extension.trim().isEmpty
            ? 'mp4'
            : media.extension
                .trim()
                .replaceAll('.', '');

    final fileName =
        '$safeTitle.$extension';

    final partialFile = File(
      '${directory.path}/$fileName.part',
    );

    if (await partialFile.exists()) {
      await partialFile.delete();
    }
  }

  // ============================================================
  // DETECT EXPIRED DIRECT URL
  // ============================================================

  bool _isExpiredUrlError(
    DioException error,
  ) {
    final status =
        error.response?.statusCode;

    return status == 403 ||
        status == 404 ||
        status == 416;
  }

  // ============================================================
  // HANDLE PAUSE / CANCEL
  // ============================================================

  Never _throwCancellation(
    CancelToken cancelToken,
  ) {
    final reason =
        cancelToken.cancelError?.message ?? '';

    if (reason == 'cancel') {
      throw const DownloadCancelledException();
    }

    throw const DownloadPausedException();
  }

  // ============================================================
  // PROGRESS NOTIFICATION
  // ============================================================

  Future<void> showProgress(
    String fileName,
    int received,
    int total,
  ) async {
    if (!_notificationsInitialized) {
      await initializeNotifications();
    }

    int progress = 0;
    bool indeterminate = true;

    if (total > 0) {
      progress =
          ((received / total) * 100)
              .clamp(0, 100)
              .round();

      indeterminate = false;
    }

    final details =
        AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription:
          'MP34 Downloader downloads',
      importance: Importance.low,
      priority: Priority.low,
      onlyAlertOnce: true,
      showProgress: true,
      maxProgress: 100,
      progress: progress,
      indeterminate: indeterminate,
    );

    await _notifications.show(
      id: 1001,
      title: 'Downloading',
      body: fileName,
      notificationDetails: NotificationDetails(
        android: details,
      ),
    );
  }

  // ============================================================
  // REFRESHING NOTIFICATION
  // ============================================================

  Future<void> showRefreshing(
    String fileName,
  ) async {
    if (!_notificationsInitialized) {
      await initializeNotifications();
    }

    const details =
        AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription:
          'MP34 Downloader downloads',
      importance: Importance.low,
      priority: Priority.low,
    );

    await _notifications.show(
      id: 1001,
      title: 'Refreshing download',
      body: fileName,
      notificationDetails: const NotificationDetails(
        android: details,
      ),
    );
  }

  // ============================================================
  // PAUSED NOTIFICATION
  // ============================================================

  Future<void> showPaused(
    String fileName,
  ) async {
    if (!_notificationsInitialized) {
      await initializeNotifications();
    }

    const details =
        AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription:
          'MP34 Downloader downloads',
      importance: Importance.low,
      priority: Priority.low,
    );

    await _notifications.show(
      id: 1001,
      title: 'Download paused',
      body: fileName,
      notificationDetails: const NotificationDetails(
        android: details,
      ),
    );
  }

  // ============================================================
  // COMPLETE NOTIFICATION
  // ============================================================

  Future<void> showComplete(
    String fileName,
  ) async {
    if (!_notificationsInitialized) {
      await initializeNotifications();
    }

    const details = AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription: 'MP34 Downloader downloads',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    );

    await _notifications.show(
      id: 1001,
      title: 'Download complete',
      body: fileName,
      notificationDetails: const NotificationDetails(
        android: details,
      ),
    );
  }

  // ============================================================
  // FAILED NOTIFICATION
  // ============================================================

  Future<void> showFailed(
    String message,
  ) async {
    if (!_notificationsInitialized) {
      await initializeNotifications();
    }

    const details = AndroidNotificationDetails(
      'downloads',
      'Downloads',
      channelDescription: 'MP34 Downloader downloads',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    );

    await _notifications.show(
      id: 1001,
      title: 'Download failed',
      body: message,
      notificationDetails: const NotificationDetails(
        android: details,
      ),
    );
  }

  // ============================================================
  // FILE NAME
  // ============================================================

  String _sanitizeFileName(
    String value,
  ) {
    String result = value.trim();

    if (result.isEmpty) {
      result = 'download';
    }

    result = result.replaceAll(
      RegExp(
        r'[<>:"/\\|?*\x00-\x1F]',
      ),
      '_',
    );

    result = result.replaceAll(
      RegExp(r'\s+'),
      ' ',
    );

    if (result.length > 120) {
      result =
          result.substring(0, 120);
    }

    return result;
  }

  // ============================================================
  // DOWNLOAD LOCATION
  // ============================================================

  String _downloadLocation(
    MediaInfo media,
  ) {
    final extension =
        media.extension.toLowerCase();

    final isAudio = [
      'mp3',
      'm4a',
      'aac',
      'wav',
      'ogg',
      'opus',
      'flac',
    ].contains(extension);

    if (isAudio) {
      return 'Music/MP34 Downloader';
    }

    return 'Movies/MP34 Downloader';
  }

  // ============================================================
  // ERROR MESSAGE
  // ============================================================

  String _messageFor(
    DioException error,
  ) {
    if (error.type ==
        DioExceptionType.connectionTimeout) {
      return 'Connection timed out.';
    }

    if (error.type ==
        DioExceptionType.receiveTimeout) {
      return 'Download timed out.';
    }

    if (error.type ==
        DioExceptionType.connectionError) {
      return 'Could not connect to the server.';
    }

    final status =
        error.response?.statusCode;

    if (status == 403) {
      return 'The direct media link has expired or access was denied.';
    }

    if (status == 404) {
      return 'The direct media link is no longer available.';
    }

    if (status == 416) {
      return 'The previous download range is no longer valid.';
    }

    return error.message ??
        'An unexpected network error occurred.';
  }
}

// ================================================================
// DOWNLOAD RESULT
// ================================================================

class DownloadResult {
  final String fileName;
  final String location;

  DownloadResult({
    required this.fileName,
    required this.location,
  });
}

// ================================================================
// API EXCEPTION
// ================================================================

class MediaApiException
    implements Exception {
  final String message;

  const MediaApiException(
    this.message,
  );

  @override
  String toString() => message;
}

// ================================================================
// PAUSE
// ================================================================

class DownloadPausedException
    implements Exception {
  const DownloadPausedException();

  @override
  String toString() =>
      'Download paused';
}

// ================================================================
// CANCEL
// ================================================================

class DownloadCancelledException
    implements Exception {
  const DownloadCancelledException();

  @override
  String toString() =>
      'Download cancelled';
}