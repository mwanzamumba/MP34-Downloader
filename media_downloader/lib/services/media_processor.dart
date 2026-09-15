import 'dart:io';

import 'package:ffmpeg_kit_flutter_new/ffmpeg_kit.dart';
import 'package:ffmpeg_kit_flutter_new/return_code.dart';

class MediaProcessor {
  /// Combines the downloaded video and audio into one MP4.
  static Future<void> mergeToMp4({
    required String videoPath,
    required String audioPath,
    required String outputPath,
  }) async {
    final command =
        '-y '
        '-i "${_escape(videoPath)}" '
        '-i "${_escape(audioPath)}" '
        '-map 0:v:0 '
        '-map 1:a:0 '
        '-c:v copy '
        '-c:a aac '
        '-b:a 128k '
        '-movflags +faststart '
        '"${_escape(outputPath)}"';

    final session = await FFmpegKit.execute(command);

    final returnCode = await session.getReturnCode();

    if (!ReturnCode.isSuccess(returnCode)) {
      final logs = await session.getAllLogsAsString();

      throw Exception(
        'Could not create MP4.\n'
        '${logs ?? ''}',
      );
    }

    if (!await File(outputPath).exists()) {
      throw Exception(
        'MP4 processing completed but the output file was not created.',
      );
    }
  }

  /// Converts the downloaded M4A/AAC audio into a real MP3.
  static Future<void> convertToMp3({
    required String audioPath,
    required String outputPath,
  }) async {
    final command =
        '-y '
        '-i "${_escape(audioPath)}" '
        '-vn '
        '-codec:a libmp3lame '
        '-b:a 192k '
        '"${_escape(outputPath)}"';

    final session = await FFmpegKit.execute(command);

    final returnCode = await session.getReturnCode();

    if (!ReturnCode.isSuccess(returnCode)) {
      final logs = await session.getAllLogsAsString();

      throw Exception(
        'Could not convert audio to MP3.\n'
        '${logs ?? ''}',
      );
    }

    if (!await File(outputPath).exists()) {
      throw Exception(
        'MP3 processing completed but the output file was not created.',
      );
    }
  }

  static String _escape(String path) {
    return path.replaceAll('"', '\\"');
  }
}