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
          json['title'] as String? ?? 'Unknown title',

      platform:
          json['platform'] as String? ?? 'Unknown',

      thumbnail:
          json['thumbnail'] as String?,

      duration:
          (json['duration'] as num?)?.toInt(),

      uploader:
          json['uploader'] as String?,

      channel:
          json['channel'] as String?,

      hasVideo:
          json['has_video'] == true,

      hasAudio:
          json['has_audio'] == true,

      recommendedVideo:
          json['recommended_video'] != null
              ? MediaFormat.fromJson(
                  json['recommended_video'],
                )
              : null,

      recommendedAudio:
          json['recommended_audio'] != null
              ? MediaFormat.fromJson(
                  json['recommended_audio'],
                )
              : null,

      videoFormats:
          (json['video_formats'] as List? ?? [])
              .map(
                (item) => MediaFormat.fromJson(
                  item,
                ),
              )
              .toList(),

      audioFormats:
          (json['audio_formats'] as List? ?? [])
              .map(
                (item) => MediaFormat.fromJson(
                  item,
                ),
              )
              .toList(),

      progressiveFormats:
          (json['progressive_formats'] as List? ?? [])
              .map(
                (item) => MediaFormat.fromJson(
                  item,
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
          json['type'] as String? ?? '',

      ext:
          json['ext'] as String?,

      formatNote:
          json['format_note'] as String?,

      width:
          (json['width'] as num?)?.toInt(),

      height:
          (json['height'] as num?)?.toInt(),

      resolution:
          json['resolution'] as String?,

      fps:
          (json['fps'] as num?)?.toDouble(),

      vcodec:
          json['vcodec'] as String?,

      acodec:
          json['acodec'] as String?,

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

    if (resolution != null) {
      return resolution!;
    }

    if (formatNote != null) {
      return formatNote!;
    }

    return ext?.toUpperCase() ?? 'Unknown';
  }

  String get sizeLabel {
    if (filesize == null) {
      return '';
    }

    final mb =
        filesize! / (1024 * 1024);

    if (mb >= 1024) {
      return '${(mb / 1024).toStringAsFixed(1)} GB';
    }

    return '${mb.toStringAsFixed(1)} MB';
  }
}