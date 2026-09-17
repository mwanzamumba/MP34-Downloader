import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/analyser.dart';

class MediaApi {
  static const String baseUrl =
      'https://mp34-downloader.onrender.com';

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

    if (response.statusCode != 200) {
      throw Exception(
        'Analysis failed: ${response.statusCode}\n${response.body}',
      );
    }

    final Map<String, dynamic> data =
        jsonDecode(response.body);

    if (data['success'] != true) {
      throw Exception(
        data['error']?.toString() ??
            'Unable to analyze this link.',
      );
    }

    return MediaInfo.fromJson(data);
  }

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
      },
      body: jsonEncode({
        'url': url,
        'format_id': formatId,
        'media_type': mediaType,
        'audio_format': audioFormat,
      }),
    );

    print('================ DOWNLOAD RESPONSE ================');
    print('STATUS: ${response.statusCode}');
    print('BODY: ${response.body}');
    print('====================================================');

    if (response.statusCode != 200) {
      throw Exception(
        'Download failed: ${response.statusCode}\n'
        '${response.body}',
      );
    }

    final Map<String, dynamic> data =
        jsonDecode(response.body);

    if (data['success'] != true) {
      throw Exception(
        data['error']?.toString() ??
            data['detail']?.toString() ??
            'Download failed.',
      );
    }

    // Backend currently returns "downloadUrl".
    String? downloadUrl =
        data['downloadUrl']?.toString();

    // Also support older naming if needed.
    downloadUrl ??=
        data['download_url']?.toString();

    downloadUrl ??=
        data['url']?.toString();

    if (downloadUrl == null ||
        downloadUrl.isEmpty) {
      throw Exception(
        'Server did not return a download URL.\n'
        'Actual response:\n${response.body}',
      );
    }

    // Already a complete URL.
    if (downloadUrl.startsWith('http://') ||
        downloadUrl.startsWith('https://')) {
      return downloadUrl;
    }

    // Backend returned a relative path.
    if (downloadUrl.startsWith('/')) {
      return '$baseUrl$downloadUrl';
    }

    return '$baseUrl/$downloadUrl';
  }
}