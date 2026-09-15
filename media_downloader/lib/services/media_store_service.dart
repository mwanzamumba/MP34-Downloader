import 'package:flutter/services.dart';

class MediaStoreService {
  static const MethodChannel _channel =
      MethodChannel('mp34_downloader/media_store');

  static Future<void> initialize() async {
    print('Initializing native MediaStore...');

    // Native MediaStore does not require a separate initialization call.
    // The Android implementation is available through the MethodChannel.

    print('Native MediaStore initialized.');
  }

  static Future<String> saveVideo({
    required String filePath,
    required String fileName,
  }) async {
    return _save(
      filePath: filePath,
      fileName: fileName,
      type: 'video',
    );
  }

  static Future<String> saveAudio({
    required String filePath,
    required String fileName,
  }) async {
    return _save(
      filePath: filePath,
      fileName: fileName,
      type: 'audio',
    );
  }

  static Future<String> _save({
    required String filePath,
    required String fileName,
    required String type,
  }) async {
    print('');
    print('========================================');
    print('NATIVE MEDIASTORE SAVE');
    print('========================================');
    print('Type: $type');
    print('File: $filePath');
    print('Name: $fileName');

    try {
      final result = await _channel.invokeMethod<String>(
        'saveFile',
        {
          'filePath': filePath,
          'fileName': fileName,
          'type': type,
        },
      );

      if (result == null || result.isEmpty) {
        throw Exception(
          'Android MediaStore returned an empty URI.',
        );
      }

      print('');
      print('========================================');
      print('NATIVE MEDIASTORE SUCCESS');
      print('URI: $result');
      print('========================================');

      return result;
    } on PlatformException catch (e) {
      print('');
      print('========================================');
      print('NATIVE MEDIASTORE ERROR');
      print('Code: ${e.code}');
      print('Message: ${e.message}');
      print('Details: ${e.details}');
      print('========================================');

      throw Exception(
        e.message ?? 'Android MediaStore failed to save the file.',
      );
    } catch (e) {
      print('');
      print('========================================');
      print('MEDIASTORE ERROR');
      print('Error: $e');
      print('========================================');

      rethrow;
    }
  }
}