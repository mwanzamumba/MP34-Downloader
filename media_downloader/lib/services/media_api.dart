import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/analyser.dart';

class MediaApi {
  // Replace this with your actual Render URL.
  static const String baseUrl =
      'https://mp34-downloader-api.onrender.com';

  Future<MediaInfo> analyse(String url) async {
    final response = await http.post(
      Uri.parse('$baseUrl/analyze'),
      headers: {
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'url': url,
      }),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      return MediaInfo.fromJson(data);
    }

    try {
      final error = jsonDecode(response.body);

      throw Exception(
        error['detail'] ??
            'Unable to analyse this media link.',
      );
    } catch (_) {
      throw Exception(
        'Unable to analyse this media link. '
        'Server returned ${response.statusCode}.',
      );
    }
  }

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

    try {
      final error = jsonDecode(response.body);

      throw Exception(
        error['detail'] ??
            'Download failed.',
      );
    } catch (_) {
      throw Exception(
        'Download failed. '
        'Server returned ${response.statusCode}.',
      );
    }
  }
}


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
        json['download_url'] as String? ?? '';

    return DownloadResult(
      success: json['success'] == true,
      platform:
          json['platform'] as String? ?? '',
      title:
          json['title'] as String? ?? '',
      mediaType:
          json['media_type'] as String? ?? '',
      formatId:
          json['format_id'] as String? ?? '',
      filename:
          json['filename'] as String? ?? '',
      size:
          (json['size'] as num?)?.toInt() ?? 0,
      downloadUrl:
          '$baseUrl$relativeUrl',
    );
  }
}