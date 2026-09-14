import 'package:dio/dio.dart';
import 'package:media_downloader/models/analyser.dart';

Future<MediaInfo> analyzeUrl(String url) async{
  final response = await Dio().post(' https://mp34-downloader-api.onrender.com', data: {'url': url});
  return MediaInfo.fromJson(response.data);
}