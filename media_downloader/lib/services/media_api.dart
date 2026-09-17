import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/analyser.dart';

class MediaApi {
  static const String baseUrl =
      'https://mp34-downloader.onrender.com';

  // ============================================================
  // ANALYSE
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

    /*
     * First check HTTP status.
     */
    if (response.statusCode != 200) {
      throw Exception(
        'Analysis failed: '
        '${response.statusCode}\n'
        '${response.body}',
      );
    }

    /*
     * Decode JSON safely.
     */
    dynamic decoded;

    try {
      decoded = jsonDecode(
        response.body,
      );
    } catch (e) {
      throw Exception(
        'Server returned invalid JSON.\n'
        'Response:\n${response.body}',
      );
    }

    if (decoded is! Map) {
      throw Exception(
        'Server returned an unexpected response.',
      );
    }

    final Map<String, dynamic> data =
        Map<String, dynamic>.from(decoded);

    /*
     * Backend-level failure.
     */
    if (data['success'] != true) {
      throw Exception(
        data['error']?.toString() ??
            data['detail']?.toString() ??
            'Unable to analyze this link.',
      );
    }

    /*
     * Parse MediaInfo.
     *
     * If parsing fails, expose the actual exception
     * instead of making the UI simply say
     * "Failed to analyze".
     */
    try {
      return MediaInfo.fromJson(
        data,
      );
    } catch (e, stackTrace) {
      print(
        '================================================',
      );

      print(
        'MEDIA ANALYSIS PARSING ERROR',
      );

      print(
        'Exception: $e',
      );

      print(
        'Stack trace: $stackTrace',
      );

      print(
        'Server response:',
      );

      print(
        response.body,
      );

      print(
        '================================================',
      );

      throw Exception(
        'The link was analyzed successfully, '
        'but the app could not read the server response.\n'
        'Error: $e',
      );
    }
  }

  // ============================================================
  // DOWNLOAD
  // ============================================================

  Future<String> download({
    required String url,
    required String formatId,
    String mediaType = 'video',
    String? audioFormat,
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

    /*
     * HTTP failure.
     */
    if (response.statusCode != 200) {
      throw Exception(
        'Download failed: '
        '${response.statusCode}\n'
        '${response.body}',
      );
    }

    dynamic decoded;

    try {
      decoded = jsonDecode(
        response.body,
      );
    } catch (e) {
      throw Exception(
        'Server returned invalid JSON '
        'after download request.\n'
        '${response.body}',
      );
    }

    if (decoded is! Map) {
      throw Exception(
        'Server returned an unexpected '
        'download response.',
      );
    }

    final Map<String, dynamic> data =
        Map<String, dynamic>.from(decoded);

    /*
     * Backend-level failure.
     */
    if (data['success'] != true) {
      throw Exception(
        data['error']?.toString() ??
            data['detail']?.toString() ??
            'Download failed.',
      );
    }

    /*
     * Support BOTH:
     *
     * downloadUrl
     *
     * and
     *
     * download_url
     *
     * This keeps Flutter compatible with either
     * backend response style.
     */
    String? downloadUrl;

    if (data['downloadUrl'] != null) {
      downloadUrl =
          data['downloadUrl'].toString();
    } else if (data['download_url'] != null) {
      downloadUrl =
          data['download_url'].toString();
    }

    if (downloadUrl == null ||
        downloadUrl.isEmpty) {
      throw Exception(
        'Server did not return a download URL.\n'
        'Response:\n${response.body}',
      );
    }

    /*
     * If backend already returned an absolute URL,
     * use it directly.
     */
    if (downloadUrl.startsWith(
      'http://',
    ) ||
        downloadUrl.startsWith(
      'https://',
    )) {
      return downloadUrl;
    }

    /*
     * Otherwise treat it as a path returned
     * by our FastAPI backend.
     */
    if (downloadUrl.startsWith('/')) {
      return '$baseUrl$downloadUrl';
    }

    return '$baseUrl/$downloadUrl';
  }
}