class MediaInfo {
  final String title;
  final String platform;
  final String? thumbnail;
  final int? duration;
  final String? uploader;
  final String? channel;

  final bool hasVideo;
  final bool hasAudio;

  final MediaFormat? recommendedVideo;
  final MediaFormat? recommendedAudio;

  final List<MediaFormat> videoFormats;
  final List<MediaFormat> audioFormats;
  final List<MediaFormat> progressiveFormats;

  MediaInfo({
    required this.title,
    required this.platform,
    this.thumbnail,
    this.duration,
    this.uploader,
    this.channel,
    required this.hasVideo,
    required this.hasAudio,
    this.recommendedVideo,
    this.recommendedAudio,
    required this.videoFormats,
    required this.audioFormats,
    required this.progressiveFormats,
  });

  factory MediaInfo.fromJson(
    Map<String, dynamic> json,
  ) {
    return MediaInfo(
      title:
          json['title']?.toString() ??
              'Unknown title',

      platform:
          json['platform']?.toString() ??
              'Unknown',

      thumbnail:
          json['thumbnail']?.toString(),

      duration:
          (json['duration'] as num?)?.toInt(),

      uploader:
          json['uploader']?.toString(),

      channel:
          json['channel']?.toString(),

      hasVideo:
          json['has_video'] == true,

      hasAudio:
          json['has_audio'] == true,

      recommendedVideo:
          json['recommended_video'] != null
              ? MediaFormat.fromJson(
                  json['recommended_video']
                      as Map<String, dynamic>,
                )
              : null,

      recommendedAudio:
          json['recommended_audio'] != null
              ? MediaFormat.fromJson(
                  json['recommended_audio']
                      as Map<String, dynamic>,
                )
              : null,

      videoFormats:
          (json['video_formats'] as List? ?? [])
              .map(
                (item) => MediaFormat.fromJson(
                  item as Map<String, dynamic>,
                ),
              )
              .toList(),

      audioFormats:
          (json['audio_formats'] as List? ?? [])
              .map(
                (item) => MediaFormat.fromJson(
                  item as Map<String, dynamic>,
                ),
              )
              .toList(),

      progressiveFormats:
          (json['progressive_formats'] as List? ?? [])
              .map(
                (item) => MediaFormat.fromJson(
                  item as Map<String, dynamic>,
                ),
              )
              .toList(),
    );
  }
}


class MediaFormat {
  final String formatId;
  final String type;

  final String? ext;
  final String? formatNote;

  final int? width;
  final int? height;

  final String? resolution;

  final double? fps;

  final String? vcodec;
  final String? acodec;

  final double? abr;
  final double? vbr;
  final double? tbr;

  final int? filesize;

  final bool hasVideo;
  final bool hasAudio;
  final bool progressive;

  MediaFormat({
    required this.formatId,
    required this.type,
    this.ext,
    this.formatNote,
    this.width,
    this.height,
    this.resolution,
    this.fps,
    this.vcodec,
    this.acodec,
    this.abr,
    this.vbr,
    this.tbr,
    this.filesize,
    required this.hasVideo,
    required this.hasAudio,
    required this.progressive,
  });

  factory MediaFormat.fromJson(
    Map<String, dynamic> json,
  ) {
    return MediaFormat(
      formatId:
          json['format_id']?.toString() ?? '',

      type:
          json['type']?.toString() ?? '',

      ext:
          json['ext']?.toString(),

      formatNote:
          json['format_note']?.toString(),

      width:
          (json['width'] as num?)?.toInt(),

      height:
          (json['height'] as num?)?.toInt(),

      resolution:
          json['resolution']?.toString(),

      fps:
          (json['fps'] as num?)?.toDouble(),

      vcodec:
          json['vcodec']?.toString(),

      acodec:
          json['acodec']?.toString(),

      abr:
          (json['abr'] as num?)?.toDouble(),

      vbr:
          (json['vbr'] as num?)?.toDouble(),

      tbr:
          (json['tbr'] as num?)?.toDouble(),

      filesize:
          (json['filesize'] as num?)?.toInt(),

      hasVideo:
          json['has_video'] == true,

      hasAudio:
          json['has_audio'] == true,

      progressive:
          json['progressive'] == true,
    );
  }

  String get qualityLabel {
    if (height != null && height! > 0) {
      return '${height}p';
    }

    if (resolution != null &&
        resolution!.isNotEmpty) {
      return resolution!;
    }

    if (formatNote != null &&
        formatNote!.isNotEmpty) {
      return formatNote!;
    }

    return ext?.toUpperCase() ?? 'UNKNOWN';
  }

  String get sizeLabel {
    if (filesize == null ||
        filesize! <= 0) {
      return '';
    }

    final mb =
        filesize! / (1024 * 1024);

    if (mb >= 1024) {
      return '${(mb / 1024).toStringAsFixed(1)} GB';
    }

    return '${mb.toStringAsFixed(1)} MB';
  }

  String get description {
    final parts = <String>[];

    if (qualityLabel.isNotEmpty) {
      parts.add(qualityLabel);
    }

    if (ext != null &&
        ext!.isNotEmpty) {
      parts.add(
        ext!.toUpperCase(),
      );
    }

    if (progressive) {
      parts.add('Video + Audio');
    } else if (hasVideo) {
      parts.add('Video');
    } else if (hasAudio) {
      parts.add('Audio');
    }

    return parts.join(' • ');
  }

  String get displayName {
    if (progressive) {
      return '$qualityLabel • Video + Audio';
    }

    if (hasVideo) {
      return '$qualityLabel • Video';
    }

    if (hasAudio) {
      return '$qualityLabel • Audio';
    }

    return qualityLabel;
  }
}