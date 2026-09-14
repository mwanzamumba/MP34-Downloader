import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:media_downloader/models/analyser.dart';

class MediaApi {
  MediaApi({Dio? client})
      : _client = client ??
            Dio(
              BaseOptions(
                baseUrl: _baseUrl,
                connectTimeout: const Duration(seconds: 15),
                receiveTimeout: const Duration(minutes: 5),
              ),
            );

  static const _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://mp34-downloader-api.onrender.com',
  );

  final Dio _client;

  // ============================================================
  // ANALYZE
  // ============================================================

  Future<MediaInfo> analyse(String url) async {
    try {
      final response = await _client.post<Map<String, dynamic>>(
        '/analyze',
        data: {
          'url': url,
        },
      );

      return MediaInfo.fromJson(
        response.data ?? const {},
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
    String url, {
    void Function(int received, int total)? onProgress,
  }) async {
    try {
      final response = await _client.post<List<int>>(
        '/download',
        data: {
          'url': url,
        },
        options: Options(
          responseType: ResponseType.bytes,
        ),
        onReceiveProgress: onProgress,
      );

      String fileName = _extractFileName(response);

      if (fileName.trim().isEmpty) {
        fileName = 'media_file';
      }

      // Get application storage.
      final directory = await getApplicationDocumentsDirectory();

      // Create Downloads folder.
      final downloadsDirectory = Directory(
        '${directory.path}/Downloads',
      );

      if (!await downloadsDirectory.exists()) {
        await downloadsDirectory.create(
          recursive: true,
        );
      }

      // Make sure we don't accidentally create a path
      // outside the Downloads folder.
      fileName = _sanitizeFileName(fileName);

      final file = File(
        '${downloadsDirectory.path}/$fileName',
      );

      final bytes = response.data ?? <int>[];

      if (bytes.isEmpty) {
        throw const MediaApiException(
          'The server returned an empty media file.',
        );
      }

      await file.writeAsBytes(
        bytes,
        flush: true,
      );

      return DownloadResult(
        fileName: fileName,
        filePath: file.path,
      );
    } on MediaApiException {
      rethrow;
    } on DioException catch (error) {
      throw MediaApiException(
        _messageFor(error),
      );
    } catch (_) {
      throw const MediaApiException(
        'Could not save the downloaded media.',
      );
    }
  }

  // ============================================================
  // GET FILE NAME
  // ============================================================

  String _extractFileName(
    Response<List<int>> response,
  ) {
    final contentDisposition =
        response.headers.value('content-disposition');

    if (contentDisposition == null) {
      return 'media_file';
    }

    final match = RegExp(
      r'filename="?([^"]+)"?',
      caseSensitive: false,
    ).firstMatch(contentDisposition);

    return match?.group(1) ?? 'media_file';
  }

  // ============================================================
  // SANITIZE FILE NAME
  // ============================================================

  String _sanitizeFileName(String fileName) {
    var cleaned = fileName.replaceAll(
      RegExp(r'[<>:"/\\|?*]'),
      '_',
    );

    cleaned = cleaned.trim();

    if (cleaned.isEmpty) {
      return 'media_file';
    }

    return cleaned;
  }

  // ============================================================
  // ERROR HANDLING
  // ============================================================

  String _messageFor(DioException error) {
    final data = error.response?.data;

    if (data is Map && data['detail'] is String) {
      return data['detail'] as String;
    }

    if (error.type == DioExceptionType.connectionTimeout) {
      return 'Connection timed out. Please try again.';
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

    if (error.response?.statusCode == 500) {
      return 'The server encountered an error while downloading.';
    }

    return 'Something went wrong while processing the media.';
  }
}

// ================================================================
// API EXCEPTION
// ================================================================

class MediaApiException implements Exception {
  const MediaApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

// ================================================================
// DOWNLOAD RESULT
// ================================================================

class DownloadResult {
  const DownloadResult({
    required this.fileName,
    required this.filePath,
  });

  final String fileName;
  final String filePath;
}