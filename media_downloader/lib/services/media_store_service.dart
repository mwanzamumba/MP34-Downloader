import 'dart:io';

import 'package:media_store_plus/media_store_plus.dart';

class MediaStoreService {
  static Future<void> initialize() async {
    await MediaStore.ensureInitialized();

    MediaStore.appFolder = 'MP34 Downloader';
  }

  static Future<SaveInfo?> saveVideo({
    required String filePath,
    required String fileName,
  }) async {
    final file = File(filePath);

    if (!await file.exists()) {
      throw Exception(
        'The final video file does not exist.',
      );
    }

    final result = await MediaStore().saveFile(
      tempFilePath: filePath,
      dirType: DirType.video,
      dirName: DirName.movies,
      relativePath: 'MP34 Downloader',
    );

    return result;
  }

  static Future<SaveInfo?> saveAudio({
    required String filePath,
    required String fileName,
  }) async {
    final file = File(filePath);

    if (!await file.exists()) {
      throw Exception(
        'The final audio file does not exist.',
      );
    }

    final result = await MediaStore().saveFile(
      tempFilePath: filePath,
      dirType: DirType.audio,
      dirName: DirName.music,
      relativePath: 'MP34 Downloader',
    );

    return result;
  }
}