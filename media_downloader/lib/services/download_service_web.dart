import 'dart:js_interop';

import 'package:dio/dio.dart';
import 'package:web/web.dart' as web;

import 'media_api.dart';

Future<void> downloadPlatform({
  required dynamic media,
  required String sourceUrl,
  required String format,
  required CancelToken cancelToken,
  required void Function(
    double progress,
    String status,
  ) onProgress,
}) async {
  try {
    // ============================================================
    // PREPARE
    // ============================================================

    onProgress(
      0.02,
      'Preparing download...',
    );

    print('');
    print('========================================');
    print('WEB DOWNLOAD');
    print('========================================');
    print('Title: ${media.title}');
    print('Format: $format');
    print('Source URL: $sourceUrl');
    print('========================================');

    // ============================================================
    // FORMAT ID
    // ============================================================

    final formatId =
        _getFormatId(
      media,
      format,
    );

    print(
      'Selected format ID: $formatId',
    );

    // ============================================================
    // ASK BACKEND TO CREATE FINAL FILE
    // ============================================================

    onProgress(
      0.05,
      'Preparing media on server...',
    );

    final api =
        MediaApi();

    final downloadUrl =
        await api.download(
      url: sourceUrl,
      formatId: formatId,
      mediaType:
          format == 'mp3'
              ? 'audio'
              : 'video',
      audioFormat:
          format == 'mp3'
              ? 'mp3'
              : null,
    );

    if (cancelToken.isCancelled) {
      throw DioException(
        requestOptions:
            RequestOptions(path: ''),
        type: DioExceptionType.cancel,
      );
    }

    print('');
    print('========================================');
    print('SERVER FILE READY');
    print('========================================');
    print('Download URL: $downloadUrl');
    print('========================================');

    // ============================================================
    // CREATE FILE NAME
    // ============================================================

    final safeName =
        _safeFileName(
      media.title,
    );

    final extension =
        format == 'mp3'
            ? 'mp3'
            : 'mp4';

    final fileName =
        '$safeName.$extension';

    // ============================================================
    // START BROWSER DOWNLOAD
    // ============================================================

    onProgress(
      0.50,
      'Starting browser download...',
    );

    final anchor =
        web.HTMLAnchorElement();

    anchor.href =
        downloadUrl;

    anchor.download =
        fileName;

    anchor.style.display =
        'none';

    web.document.body
        ?.appendChild(anchor);

    anchor.click();

    anchor.remove();

    // ============================================================
    // COMPLETE
    // ============================================================

    onProgress(
      1.0,
      'Download started',
    );

    print('');
    print('========================================');
    print('WEB DOWNLOAD STARTED');
    print('========================================');
  } catch (e) {
    print('');
    print('========================================');
    print('WEB DOWNLOAD ERROR');
    print('========================================');
    print(e);
    print('========================================');

    rethrow;
  }
}

// ================================================================
// FORMAT ID
// ================================================================

String _getFormatId(
  dynamic media,
  String format,
) {
  if (format == 'mp3') {
    final audio =
        media.audio;

    if (audio == null) {
      throw Exception(
        'No audio format is available.',
      );
    }

    final id =
        audio.formatId.toString();

    if (id.isEmpty) {
      throw Exception(
        'Audio format ID is empty.',
      );
    }

    return id;
  }

  final video =
      media.video;

  if (video == null) {
    throw Exception(
      'No video format is available.',
    );
  }

  final id =
      video.formatId.toString();

  if (id.isEmpty) {
    throw Exception(
      'Video format ID is empty.',
    );
  }

  return id;
}

// ================================================================
// SAFE FILE NAME
// ================================================================

String _safeFileName(
  String name,
) {
  var value =
      name.trim();

  if (value.isEmpty) {
    value =
        'MP34_Download';
  }

  value = value.replaceAll(
    RegExp(
      r'[<>:"/\\|?*\x00-\x1F]',
    ),
    '_',
  );

  if (value.length > 80) {
    value =
        value.substring(0, 80);
  }

  return value;
}