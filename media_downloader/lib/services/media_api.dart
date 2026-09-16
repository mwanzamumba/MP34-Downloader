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
        data['error'] ?? 'Unable to analyze this link.',
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

    if (response.statusCode != 200) {
      throw Exception(
        'Download failed: ${response.statusCode}\n${response.body}',
      );
    }

    final Map<String, dynamic> data =
        jsonDecode(response.body);

    if (data['success'] != true) {
      throw Exception(
        data['error'] ?? 'Download failed.',
      );
    }

    final String? downloadUrl =
        data['download_url']?.toString();

    if (downloadUrl == null || downloadUrl.isEmpty) {
      throw Exception(
        'Server did not return a download URL.',
      );
    }

    if (downloadUrl.startsWith('http')) {
      return downloadUrl;
    }

    return '$baseUrl$downloadUrl';
  }
}