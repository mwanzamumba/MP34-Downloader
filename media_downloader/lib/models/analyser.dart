class MediaInfo {
  final bool success;
  final String title;
  final String platform;
  final String? thumbnail;
  final int? duration;

  final List<MediaFormat> formats;
  final List<MediaFormat> videoFormats;
  final List<MediaFormat> audioFormats;
  final List<MediaFormat> progressiveFormats;

  final MediaFormat? recommendedVideo;
  final MediaFormat? recommendedAudio;

  MediaInfo({
    required this.success,
    required this.title,
    required this.platform,
    this.thumbnail,
    this.duration,
    required this.formats,
    required this.videoFormats,
    required this.audioFormats,
    required this.progressiveFormats,
    this.recommendedVideo,
    this.recommendedAudio,
  });

  factory MediaInfo.fromJson(Map<String, dynamic> json) {
    final List<MediaFormat> parsedFormats =
        _parseFormats(json['formats']);

    /*
     * If the backend ever sends the separated lists without
     * a complete "formats" list, include them as well.
     */
    final List<MediaFormat> backendVideoFormats =
        _parseFormats(json['video_formats']);

    final List<MediaFormat> backendAudioFormats =
        _parseFormats(json['audio_formats']);

    /*
     * Use formats as the main source.
     *
     * If formats is empty, fall back to the separate
     * backend lists.
     */
    final List<MediaFormat> allFormats = [];

    void addUnique(MediaFormat format) {
      if (format.formatId.isEmpty) {
        return;
      }

      final bool alreadyExists = allFormats.any(
        (existing) =>
            existing.formatId == format.formatId,
      );

      if (!alreadyExists) {
        allFormats.add(format);
      }
    }

    for (final format in parsedFormats) {
      addUnique(format);
    }

    for (final format in backendVideoFormats) {
      addUnique(format);
    }

    for (final format in backendAudioFormats) {
      addUnique(format);
    }

    /*
     * Build video/audio/progressive lists from the
     * actual codec information.
     */
    final List<MediaFormat> parsedVideoFormats =
        allFormats.where((format) {
      return format.hasVideo;
    }).toList();

    final List<MediaFormat> parsedAudioFormats =
        allFormats.where((format) {
      return format.hasAudio && !format.hasVideo;
    }).toList();

    final List<MediaFormat> parsedProgressiveFormats =
        allFormats.where((format) {
      return format.hasVideo && format.hasAudio;
    }).toList();

    /*
     * Backend recommendations.
     */
    MediaFormat? recommendedVideo;
    MediaFormat? recommendedAudio;

    final dynamic recommendedVideoJson =
        json['recommended_video'];

    if (recommendedVideoJson is Map) {
      recommendedVideo =
          MediaFormat.fromJson(
        Map<String, dynamic>.from(
          recommendedVideoJson,
        ),
      );
    }

    final dynamic recommendedAudioJson =
        json['recommended_audio'];

    if (recommendedAudioJson is Map) {
      recommendedAudio =
          MediaFormat.fromJson(
        Map<String, dynamic>.from(
          recommendedAudioJson,
        ),
      );
    }

    /*
     * If backend recommendation is missing,
     * choose locally.
     */
    recommendedVideo ??= _bestVideo(
      parsedVideoFormats,
    );

    recommendedAudio ??= _bestAudio(
      parsedAudioFormats,
    );

    /*
     * Duration.
     */
    int? parsedDuration;

    final dynamic durationValue =
        json['duration'];

    if (durationValue is num) {
      parsedDuration =
          durationValue.toInt();
    } else if (durationValue != null) {
      parsedDuration =
          int.tryParse(
        durationValue.toString(),
      );
    }

    return MediaInfo(
      success: json['success'] == true,
      title:
          json['title']?.toString() ??
              'Unknown title',
      platform:
          json['platform']?.toString() ??
              'Unknown',
      thumbnail:
          _nullableString(
        json['thumbnail'],
      ),
      duration: parsedDuration,
      formats: allFormats,
      videoFormats: parsedVideoFormats,
      audioFormats: parsedAudioFormats,
      progressiveFormats:
          parsedProgressiveFormats,
      recommendedVideo:
          recommendedVideo,
      recommendedAudio:
          recommendedAudio,
    );
  }

  // ============================================================
  // FORMAT PARSER
  // ============================================================

  static List<MediaFormat> _parseFormats(
    dynamic value,
  ) {
    final List<MediaFormat> result = [];

    if (value is! List) {
      return result;
    }

    for (final item in value) {
      if (item is Map) {
        try {
          final format =
              MediaFormat.fromJson(
            Map<String, dynamic>.from(item),
          );

          if (format.formatId.isNotEmpty) {
            result.add(format);
          }
        } catch (_) {
          /*
           * Ignore one malformed format instead of
           * breaking the entire analysis response.
           */
        }
      }
    }

    return result;
  }

  // ============================================================
  // COMPATIBILITY GETTERS
  // ============================================================

  MediaFormat? get video {
    return getVideo();
  }

  MediaFormat? get audio {
    return getAudio();
  }

  // ============================================================
  // VIDEO
  // ============================================================

  MediaFormat? getVideo() {
    if (recommendedVideo != null) {
      return recommendedVideo;
    }

    if (progressiveFormats.isNotEmpty) {
      return _bestVideo(
        progressiveFormats,
      );
    }

    if (videoFormats.isNotEmpty) {
      return _bestVideo(
        videoFormats,
      );
    }

    return null;
  }

  // ============================================================
  // AUDIO
  // ============================================================

  MediaFormat? getAudio() {
    if (recommendedAudio != null) {
      return recommendedAudio;
    }

    if (audioFormats.isNotEmpty) {
      return _bestAudio(
        audioFormats,
      );
    }

    if (progressiveFormats.isNotEmpty) {
      return _bestAudio(
        progressiveFormats,
      );
    }

    return null;
  }

  // ============================================================
  // COMPATIBILITY METHODS
  // ============================================================

  MediaFormat? getBestVideo() {
    return getVideo();
  }

  MediaFormat? getBestAudio() {
    return getAudio();
  }

  // ============================================================
  // BEST VIDEO
  // ============================================================

  static MediaFormat? _bestVideo(
    List<MediaFormat> formats,
  ) {
    if (formats.isEmpty) {
      return null;
    }

    final List<MediaFormat> sorted =
        List<MediaFormat>.from(formats);

    sorted.sort(
      (a, b) {
        final int heightA =
            a.height ?? 0;

        final int heightB =
            b.height ?? 0;

        return heightB.compareTo(
          heightA,
        );
      },
    );

    return sorted.first;
  }

  // ============================================================
  // BEST AUDIO
  // ============================================================

  static MediaFormat? _bestAudio(
    List<MediaFormat> formats,
  ) {
    if (formats.isEmpty) {
      return null;
    }

    final List<MediaFormat> sorted =
        List<MediaFormat>.from(formats);

    sorted.sort(
      (a, b) {
        final int bitrateA =
            a.audioBitrate ?? 0;

        final int bitrateB =
            b.audioBitrate ?? 0;

        return bitrateB.compareTo(
          bitrateA,
        );
      },
    );

    return sorted.first;
  }

  // ============================================================
  // STRING HELPER
  // ============================================================

  static String? _nullableString(
    dynamic value,
  ) {
    if (value == null) {
      return null;
    }

    final String text =
        value.toString().trim();

    if (text.isEmpty ||
        text == 'null' ||
        text == 'none') {
      return null;
    }

    return text;
  }
}

// ================================================================
// MEDIA FORMAT
// ================================================================

class MediaFormat {
  final String formatId;
  final String? ext;
  final String? formatNote;

  final int? width;
  final int? height;

  final double? fps;

  final String? vcodec;
  final String? acodec;

  final int? filesize;
  final int? filesizeApprox;

  final int? audioBitrate;

  final String? url;

  final bool hasVideo;
  final bool hasAudio;

  MediaFormat({
    required this.formatId,
    this.ext,
    this.formatNote,
    this.width,
    this.height,
    this.fps,
    this.vcodec,
    this.acodec,
    this.filesize,
    this.filesizeApprox,
    this.audioBitrate,
    this.url,
    required this.hasVideo,
    required this.hasAudio,
  });

  factory MediaFormat.fromJson(
    Map<String, dynamic> json,
  ) {
    final String? parsedVcodec =
        _nullableString(
      json['vcodec'],
    );

    final String? parsedAcodec =
        _nullableString(
      json['acodec'],
    );

    final bool parsedHasVideo =
        json['has_video'] == true ||
        (
          parsedVcodec != null &&
          parsedVcodec.isNotEmpty &&
          parsedVcodec != 'none'
        );

    final bool parsedHasAudio =
        json['has_audio'] == true ||
        (
          parsedAcodec != null &&
          parsedAcodec.isNotEmpty &&
          parsedAcodec != 'none'
        );

    return MediaFormat(
      formatId:
          json['format_id']?.toString() ??
              '',

      ext:
          _nullableString(
        json['ext'],
      ),

      formatNote:
          _nullableString(
        json['format_note'],
      ),

      width:
          _toInt(
        json['width'],
      ),

      height:
          _toInt(
        json['height'],
      ),

      fps:
          _toDouble(
        json['fps'],
      ),

      vcodec:
          parsedVcodec,

      acodec:
          parsedAcodec,

      filesize:
          _toInt(
        json['filesize'],
      ),

      filesizeApprox:
          _toInt(
        json['filesize_approx'],
      ),

      audioBitrate:
          _toInt(
        json['abr'],
      ),

      url:
          _nullableString(
        json['url'],
      ),

      hasVideo:
          parsedHasVideo,

      hasAudio:
          parsedHasAudio,
    );
  }

  // ============================================================
  // FILE SIZE
  // ============================================================

  int? get effectiveFilesize {
    return filesize ?? filesizeApprox;
  }

  String get sizeLabel {
    final int? size =
        effectiveFilesize;

    if (size == null || size <= 0) {
      return 'Size unknown';
    }

    final double mb =
        size / (1024 * 1024);

    if (mb < 1024) {
      return '${mb.toStringAsFixed(1)} MB';
    }

    final double gb =
        mb / 1024;

    return '${gb.toStringAsFixed(2)} GB';
  }

  // ============================================================
  // RESOLUTION
  // ============================================================

  String get resolutionLabel {
    if (height != null && height! > 0) {
      return '${height}p';
    }

    if (width != null &&
        width! > 0 &&
        height != null &&
        height! > 0) {
      return '${width}x$height';
    }

    return 'Unknown';
  }

  // ============================================================
  // TYPE
  // ============================================================

  String get typeLabel {
    if (hasVideo && hasAudio) {
      return 'Video + Audio';
    }

    if (hasVideo) {
      return 'Video';
    }

    if (hasAudio) {
      return 'Audio';
    }

    return 'Unknown';
  }

  // ============================================================
  // HELPERS
  // ============================================================

  static String? _nullableString(
    dynamic value,
  ) {
    if (value == null) {
      return null;
    }

    final String text =
        value.toString().trim();

    if (text.isEmpty ||
        text == 'null' ||
        text == 'none') {
      return null;
    }

    return text;
  }

  static int? _toInt(
    dynamic value,
  ) {
    if (value == null) {
      return null;
    }

    if (value is int) {
      return value;
    }

    if (value is num) {
      return value.toInt();
    }

    return int.tryParse(
      value.toString(),
    );
  }

  static double? _toDouble(
    dynamic value,
  ) {
    if (value == null) {
      return null;
    }

    if (value is double) {
      return value;
    }

    if (value is num) {
      return value.toDouble();
    }

    return double.tryParse(
      value.toString(),
    );
  }
}