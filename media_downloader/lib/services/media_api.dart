import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/analyser.dart';

class MediaApi {
  static const String baseUrl =
      'https://mp34-downloader.onrender.com';

  // ============================================================
  // ANALYSE MEDIA
  // ============================================================

  Future<MediaInfo> analyse(String url) async {
    final response = await http.post(
      Uri.parse('$baseUrl/analyze'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({
        'url': url,
      }),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      return MediaInfo.fromJson(data);
    }

    throw Exception(
      _getErrorMessage(
        response,
        'Unable to analyze this media link.',
      ),
    );
  }

  // ============================================================
  // DOWNLOAD
  // ============================================================

  Future<DownloadResult> download({
    required String url,
    String? formatId,
    String mediaType = 'video',
    String audioFormat = 'mp3',
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/download'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({
        'url': url,
        'format_id': formatId,
        'media_type': mediaType,
        'audio_format': audioFormat,
      }),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      return DownloadResult.fromJson(
        data,
        baseUrl,
      );
    }

    throw Exception(
      _getErrorMessage(
        response,
        'Download failed.',
      ),
    );
  }

  // ============================================================
  // SERVER VERSION
  // ============================================================

  Future<Map<String, dynamic>> getVersion() async {
    final response = await http.get(
      Uri.parse('$baseUrl/version'),
      headers: {
        'Accept': 'application/json',
      },
    );

    if (response.statusCode == 200) {
      return jsonDecode(response.body)
          as Map<String, dynamic>;
    }

    throw Exception(
      _getErrorMessage(
        response,
        'Unable to connect to the media server.',
      ),
    );
  }

  // ============================================================
  // ERROR HANDLING
  // ============================================================

  String _getErrorMessage(
    http.Response response,
    String fallback,
  ) {
    try {
      final data = jsonDecode(response.body);

      if (data is Map &&
          data['detail'] != null) {
        return data['detail'].toString();
      }
    } catch (_) {
      // Ignore invalid JSON.
    }

    return '$fallback Server returned ${response.statusCode}.';
  }
}


// ============================================================
// DOWNLOAD RESULT
// ============================================================

class DownloadResult {
  final bool success;
  final String platform;
  final String title;
  final String mediaType;
  final String formatId;
  final String filename;
  final int size;
  final String downloadUrl;

  DownloadResult({
    required this.success,
    required this.platform,
    required this.title,
    required this.mediaType,
    required this.formatId,
    required this.filename,
    required this.size,
    required this.downloadUrl,
  });

  factory DownloadResult.fromJson(
    Map<String, dynamic> json,
    String baseUrl,
  ) {
    final relativeUrl =
        json['download_url']?.toString() ?? '';

    final fullUrl =
        relativeUrl.startsWith('http')
            ? relativeUrl
            : '$baseUrl$relativeUrl';

    return DownloadResult(
      success: json['success'] == true,
      platform:
          json['platform']?.toString() ?? '',
      title:
          json['title']?.toString() ?? '',
      mediaType:
          json['media_type']?.toString() ?? '',
      formatId:
          json['format_id']?.toString() ?? '',
      filename:
          json['filename']?.toString() ?? '',
      size:
          (json['size'] as num?)?.toInt() ?? 0,
      downloadUrl: fullUrl,
    );
  }

  double get sizeInMB {
    return size / (1024 * 1024);
  }

  String get sizeLabel {
    if (size <= 0) {
      return 'Unknown size';
    }

    if (size >= 1024 * 1024 * 1024) {
      return '${(size / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
    }

    return '${sizeInMB.toStringAsFixed(1)} MB';
  }
}