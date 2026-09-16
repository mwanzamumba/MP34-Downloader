class MediaInfo {
  final bool success;
  final String title;
  final String platform;
  final String? thumbnail;
  final int? duration;
  final String? uploader;
  final String? channel;
  final String? webpageUrl;

  final bool hasVideo;
  final bool hasAudio;

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
    this.uploader,
    this.channel,
    this.webpageUrl,
    required this.hasVideo,
    required this.hasAudio,
    required this.videoFormats,
    required this.audioFormats,
    required this.progressiveFormats,
    this.recommendedVideo,
    this.recommendedAudio,
  });

  factory MediaInfo.fromJson(
    Map<String, dynamic> json,
  ) {
    return MediaInfo(
      success: json['success'] == true,

      title: json['title']?.toString() ??
          'Unknown title',

      platform: json['platform']?.toString() ??
          'Unknown',

      thumbnail:
          json['thumbnail']?.toString(),

      // Safely handles both:
      // 357
      // 357.0
      duration: json['duration'] is num
          ? (json['duration'] as num).toInt()
          : null,

      uploader:
          json['uploader']?.toString(),

      channel:
          json['channel']?.toString(),

      webpageUrl:
          json['webpage_url']?.toString(),

      hasVideo:
          json['has_video'] == true,

      hasAudio:
          json['has_audio'] == true,

      videoFormats:
          _parseFormats(
        json['video_formats'],
      ),

      audioFormats:
          _parseFormats(
        json['audio_formats'],
      ),

      progressiveFormats:
          _parseFormats(
        json['progressive_formats'],
      ),

      recommendedVideo:
          _parseSingleFormat(
        json['recommended_video'],
      ),

      recommendedAudio:
          _parseSingleFormat(
        json['recommended_audio'],
      ),
    );
  }

  static List<MediaFormat> _parseFormats(
    dynamic value,
  ) {
    if (value is! List) {
      return [];
    }

    return value
        .whereType<Map>()
        .map(
          (item) => MediaFormat.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  static MediaFormat? _parseSingleFormat(
    dynamic value,
  ) {
    if (value is! Map) {
      return null;
    }

    return MediaFormat.fromJson(
      Map<String, dynamic>.from(value),
    );
  }
}


class MediaFormat {
  final String formatId;
  final String ext;
  final String? resolution;

  final int? width;
  final int? height;
  final double? fps;

  final int? filesize;

  final String? vcodec;
  final String? acodec;

  final double? abr;
  final double? vbr;

  final String? formatNote;
  final String? protocol;
  final String? formatType;

  MediaFormat({
    required this.formatId,
    required this.ext,
    this.resolution,
    this.width,
    this.height,
    this.fps,
    this.filesize,
    this.vcodec,
    this.acodec,
    this.abr,
    this.vbr,
    this.formatNote,
    this.protocol,
    this.formatType,
  });

  factory MediaFormat.fromJson(
    Map<String, dynamic> json,
  ) {
    return MediaFormat(

      formatId:
          json['format_id']?.toString() ??
              '',

      ext:
          json['ext']?.toString() ??
              '',

      resolution:
          json['resolution']?.toString(),

      // Safely handles int and double.
      width:
          json['width'] is num
              ? (json['width'] as num).toInt()
              : null,

      height:
          json['height'] is num
              ? (json['height'] as num).toInt()
              : null,

      fps:
          json['fps'] is num
              ? (json['fps'] as num).toDouble()
              : null,

      filesize:
          json['filesize'] is num
              ? (json['filesize'] as num).toInt()
              : null,

      vcodec:
          json['vcodec']?.toString(),

      acodec:
          json['acodec']?.toString(),

      abr:
          json['abr'] is num
              ? (json['abr'] as num).toDouble()
              : null,

      vbr:
          json['vbr'] is num
              ? (json['vbr'] as num).toDouble()
              : null,

      formatNote:
          json['format_note']?.toString(),

      protocol:
          json['protocol']?.toString(),

      formatType:
          json['format_type']?.toString(),
    );
  }


  // ==========================================================
  // VIDEO CHECK
  // ==========================================================

  bool get hasVideo {

    return vcodec != null &&
        vcodec!.isNotEmpty &&
        vcodec != 'none';
  }


  // ==========================================================
  // AUDIO CHECK
  // ==========================================================

  bool get hasAudio {

    return acodec != null &&
        acodec!.isNotEmpty &&
        acodec != 'none';
  }


  // ==========================================================
  // PROGRESSIVE CHECK
  // ==========================================================

  bool get isProgressive {

    return hasVideo &&
        hasAudio;
  }


  // ==========================================================
  // DISPLAY RESOLUTION
  // ==========================================================

  String get displayResolution {

    if (
      formatNote != null &&
      formatNote!.isNotEmpty
    ) {

      return formatNote!;
    }

    if (
      resolution != null &&
      resolution!.isNotEmpty
    ) {

      return resolution!;
    }

    if (height != null) {

      return '${height}p';
    }

    return 'Unknown quality';
  }


  // ==========================================================
  // DISPLAY FILE SIZE
  // ==========================================================

  String get displaySize {

    if (
      filesize == null ||
      filesize! <= 0
    ) {

      return 'Unknown size';
    }

    final double mb =
        filesize! /
        (1024 * 1024);

    if (mb >= 1024) {

      return '${(mb / 1024).toStringAsFixed(1)} GB';
    }

    return '${mb.toStringAsFixed(1)} MB';
  }


  // ==========================================================
  // DISPLAY TYPE
  // ==========================================================

  String get displayType {

    if (isProgressive) {

      return 'Video + Audio';
    }

    if (hasVideo) {

      return 'Video only';
    }

    if (hasAudio) {

      return 'Audio only';
    }

    return 'Unknown';
  }
}