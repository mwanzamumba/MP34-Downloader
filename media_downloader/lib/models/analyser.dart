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

  factory MediaInfo.fromJson(Map<String, dynamic> json) {
    return MediaInfo(
      success: json['success'] ?? false,
      title: json['title'] ?? 'Unknown title',
      platform: json['platform'] ?? 'Unknown',
      thumbnail: json['thumbnail'],
      duration: json['duration'],
      uploader: json['uploader'],
      channel: json['channel'],
      webpageUrl: json['webpage_url'],

      hasVideo: json['has_video'] ?? false,
      hasAudio: json['has_audio'] ?? false,

      videoFormats: (json['video_formats'] as List? ?? [])
          .map((item) => MediaFormat.fromJson(item))
          .toList(),

      audioFormats: (json['audio_formats'] as List? ?? [])
          .map((item) => MediaFormat.fromJson(item))
          .toList(),

      progressiveFormats: (json['progressive_formats'] as List? ?? [])
          .map((item) => MediaFormat.fromJson(item))
          .toList(),

      recommendedVideo: json['recommended_video'] != null
          ? MediaFormat.fromJson(json['recommended_video'])
          : null,

      recommendedAudio: json['recommended_audio'] != null
          ? MediaFormat.fromJson(json['recommended_audio'])
          : null,
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

  factory MediaFormat.fromJson(Map<String, dynamic> json) {
    return MediaFormat(
      formatId: json['format_id']?.toString() ?? '',
      ext: json['ext']?.toString() ?? '',
      resolution: json['resolution']?.toString(),

      width: json['width'] is num
          ? (json['width'] as num).toInt()
          : null,

      height: json['height'] is num
          ? (json['height'] as num).toInt()
          : null,

      fps: json['fps'] is num
          ? (json['fps'] as num).toDouble()
          : null,

      filesize: json['filesize'] is num
          ? (json['filesize'] as num).toInt()
          : null,

      vcodec: json['vcodec']?.toString(),
      acodec: json['acodec']?.toString(),

      abr: json['abr'] is num
          ? (json['abr'] as num).toDouble()
          : null,

      vbr: json['vbr'] is num
          ? (json['vbr'] as num).toDouble()
          : null,

      formatNote: json['format_note']?.toString(),
      protocol: json['protocol']?.toString(),
      formatType: json['format_type']?.toString(),
    );
  }

  bool get hasVideo {
    return vcodec != null &&
        vcodec!.isNotEmpty &&
        vcodec != 'none';
  }

  bool get hasAudio {
    return acodec != null &&
        acodec!.isNotEmpty &&
        acodec != 'none';
  }

  bool get isProgressive {
    return hasVideo && hasAudio;
  }

  String get displayResolution {
    if (formatNote != null && formatNote!.isNotEmpty) {
      return formatNote!;
    }

    if (resolution != null && resolution!.isNotEmpty) {
      return resolution!;
    }

    if (height != null) {
      return '${height}p';
    }

    return 'Unknown quality';
  }

  String get displaySize {
    if (filesize == null || filesize! <= 0) {
      return 'Unknown size';
    }

    final mb = filesize! / (1024 * 1024);

    if (mb >= 1024) {
      return '${(mb / 1024).toStringAsFixed(1)} GB';
    }

    return '${mb.toStringAsFixed(1)} MB';
  }

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