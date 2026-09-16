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
    final List<MediaFormat> parsedFormats = [];

    final dynamic formatsJson = json['formats'];

    if (formatsJson is List) {
      for (final item in formatsJson) {
        if (item is Map<String, dynamic>) {
          parsedFormats.add(
            MediaFormat.fromJson(item),
          );
        } else if (item is Map) {
          parsedFormats.add(
            MediaFormat.fromJson(
              Map<String, dynamic>.from(item),
            ),
          );
        }
      }
    }

    final List<MediaFormat> parsedVideoFormats =
        parsedFormats.where((format) {
      return format.hasVideo;
    }).toList();

    final List<MediaFormat> parsedAudioFormats =
        parsedFormats.where((format) {
      return format.hasAudio && !format.hasVideo;
    }).toList();

    final List<MediaFormat> parsedProgressiveFormats =
        parsedFormats.where((format) {
      return format.hasVideo && format.hasAudio;
    }).toList();

    MediaFormat? recommendedVideo;

    MediaFormat? recommendedAudio;

    /*
     * Try to read recommendations from the backend.
     */
    if (json['recommended_video'] is Map) {
      recommendedVideo = MediaFormat.fromJson(
        Map<String, dynamic>.from(
          json['recommended_video'],
        ),
      );
    }

    if (json['recommended_audio'] is Map) {
      recommendedAudio = MediaFormat.fromJson(
        Map<String, dynamic>.from(
          json['recommended_audio'],
        ),
      );
    }

    /*
     * If backend did not provide recommended video,
     * choose one locally.
     */
    if (recommendedVideo == null) {
      if (parsedProgressiveFormats.isNotEmpty) {
        recommendedVideo = _bestVideo(
          parsedProgressiveFormats,
        );
      } else if (parsedVideoFormats.isNotEmpty) {
        recommendedVideo = _bestVideo(
          parsedVideoFormats,
        );
      }
    }

    /*
     * If backend did not provide recommended audio,
     * choose one locally.
     */
    if (recommendedAudio == null) {
      if (parsedAudioFormats.isNotEmpty) {
        recommendedAudio = _bestAudio(
          parsedAudioFormats,
        );
      } else if (parsedProgressiveFormats.isNotEmpty) {
        recommendedAudio = _bestAudio(
          parsedProgressiveFormats,
        );
      }
    }

    /*
     * Duration can come as int, double or null.
     */
    int? parsedDuration;

    final dynamic durationValue = json['duration'];

    if (durationValue is num) {
      parsedDuration = durationValue.toInt();
    } else if (durationValue != null) {
      parsedDuration = int.tryParse(
        durationValue.toString(),
      );
    }

    return MediaInfo(
      success: json['success'] == true,
      title: json['title']?.toString() ?? 'Unknown title',
      platform: json['platform']?.toString() ?? 'Unknown',
      thumbnail: json['thumbnail']?.toString(),
      duration: parsedDuration,
      formats: parsedFormats,
      videoFormats: parsedVideoFormats,
      audioFormats: parsedAudioFormats,
      progressiveFormats: parsedProgressiveFormats,
      recommendedVideo: recommendedVideo,
      recommendedAudio: recommendedAudio,
    );
  }

  // ============================================================
  // COMPATIBILITY GETTERS
  // ============================================================

  /*
   * This fixes:
   *
   * NoSuchMethodError:
   * Class 'MediaInfo' has no instance getter 'video'
   */
  MediaFormat? get video {
    return getVideo();
  }

  /*
   * Compatibility getter for old UI/business logic.
   */
  MediaFormat? get audio {
    return getAudio();
  }

  // ============================================================
  // VIDEO
  // ============================================================

  MediaFormat? getVideo() {
    /*
     * First use backend recommendation.
     */
    if (recommendedVideo != null) {
      return recommendedVideo;
    }

    /*
     * Prefer progressive formats because they contain
     * both video and audio.
     */
    if (progressiveFormats.isNotEmpty) {
      return _bestVideo(
        progressiveFormats,
      );
    }

    /*
     * Otherwise use video-only formats.
     */
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
    /*
     * First use backend recommendation.
     */
    if (recommendedAudio != null) {
      return recommendedAudio;
    }

    /*
     * Prefer audio-only formats.
     */
    if (audioFormats.isNotEmpty) {
      return _bestAudio(
        audioFormats,
      );
    }

    /*
     * Fall back to progressive formats.
     */
    if (progressiveFormats.isNotEmpty) {
      return _bestAudio(
        progressiveFormats,
      );
    }

    return null;
  }

  // ============================================================
  // OTHER COMPATIBILITY METHODS
  // ============================================================

  MediaFormat? getBestVideo() {
    return getVideo();
  }

  MediaFormat? getBestAudio() {
    return getAudio();
  }

  // ============================================================
  // BEST VIDEO FORMAT
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
        final int heightA = a.height ?? 0;
        final int heightB = b.height ?? 0;

        return heightB.compareTo(heightA);
      },
    );

    return sorted.first;
  }

  // ============================================================
  // BEST AUDIO FORMAT
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

    /*
     * Determine whether the format contains video.
     */
    final bool parsedHasVideo =
        json['has_video'] == true ||
        (
          parsedVcodec != null &&
          parsedVcodec.isNotEmpty &&
          parsedVcodec != 'none'
        );

    /*
     * Determine whether the format contains audio.
     */
    final bool parsedHasAudio =
        json['has_audio'] == true ||
        (
          parsedAcodec != null &&
          parsedAcodec.isNotEmpty &&
          parsedAcodec != 'none'
        );

    return MediaFormat(
      formatId:
          json['format_id']?.toString() ?? '',

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

  // ============================================================
  // DISPLAY SIZE
  // ============================================================

  String get sizeLabel {
    final int? size = effectiveFilesize;

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
  // FORMAT TYPE
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