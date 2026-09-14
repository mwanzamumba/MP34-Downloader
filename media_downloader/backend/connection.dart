import 'package:dio/dio.dart';
import 'package:media_downloader/models/analyser.dart';

Future<MediaInfo> analyzeUrl(String url) async{
  final response = await Dio().post(' http://0.0.0.0:8000/analyze', data: {'url': url});
  return MediaInfo.fromJson(response.data);
}