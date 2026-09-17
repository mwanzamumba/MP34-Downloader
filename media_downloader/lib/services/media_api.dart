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

    if (response.statusCode != 200) {
      throw Exception(
        'Analysis failed: '
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
        'Server returned invalid JSON.\n'
        '${response.body}',
      );
    }

    if (decoded is! Map) {
      throw Exception(
        'Server returned an unexpected response.',
      );
    }

    final Map<String, dynamic> data =
        Map<String, dynamic>.from(decoded);

    if (data['success'] != true) {
      throw Exception(
        data['error']?.toString() ??
            data['detail']?.toString() ??
            'Unable to analyze this link.',
      );
    }

    try {
      return MediaInfo.fromJson(
        data,
      );
    } catch (e, stackTrace) {
      print(
        'MEDIA ANALYSIS PARSING ERROR: $e',
      );

      print(
        stackTrace,
      );

      print(
        'SERVER RESPONSE: ${response.body}',
      );

      throw Exception(
        'The link was analyzed successfully, '
        'but the app could not read the response.\n'
        '$e',
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

    print(
      'DOWNLOAD STATUS: ${response.statusCode}',
    );

    print(
      'DOWNLOAD RESPONSE: ${response.body}',
    );

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
        'Server returned invalid JSON.\n'
        '${response.body}',
      );
    }

    if (decoded is! Map) {
      throw Exception(
        'Server returned an unexpected download response.\n'
        '${response.body}',
      );
    }

    final Map<String, dynamic> data =
        Map<String, dynamic>.from(decoded);

    if (data['success'] != true) {
      throw Exception(
        data['error']?.toString() ??
            data['detail']?.toString() ??
            'Download failed.',
      );
    }

    /*
     * Our backend uses:
     *
     * downloadUrl
     */
    final dynamic rawDownloadUrl =
        data['downloadUrl'];

    if (rawDownloadUrl == null) {
      throw Exception(
        'Server did not return a download URL.\n'
        'Actual response:\n'
        '${response.body}',
      );
    }

    final String downloadUrl =
        rawDownloadUrl.toString().trim();

    if (downloadUrl.isEmpty) {
      throw Exception(
        'Server returned an empty download URL.\n'
        'Actual response:\n'
        '${response.body}',
      );
    }

    /*
     * Absolute URL.
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
     * Relative URL.
     */
    if (downloadUrl.startsWith('/')) {
      return '$baseUrl$downloadUrl';
    }

    return '$baseUrl/$downloadUrl';
  }
}