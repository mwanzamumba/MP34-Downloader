import 'package:dio/dio.dart';
import 'package:media_downloader/models/analyser.dart';

Future<dynamic> analyzeUrl(String url) async {
  final dio = Dio();

  final response = await dio.post(
    'https://mp34-downloader-api.onrender.com/analyze',
    data: {
      'url': url,
    },
  );

  return response.data;
}