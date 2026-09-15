class MediaAnalysis {
  final String title;
  final String thumbnail;
  final String platform;
  final String sourceUrl;

  final VideoStreamInfo video;
  final AudioStreamInfo audio;

  final List<String> availableFormats;

  MediaAnalysis({
    required this.title,
    required this.thumbnail,
    required this.platform,
    required this.sourceUrl,
    required this.video,
    required this.audio,
    required this.availableFormats,
  });

  factory MediaAnalysis.fromJson(Map<String, dynamic> json) {
    return MediaAnalysis(
      title: json['title'] ?? 'Untitled media',
      thumbnail: json['thumbnail'] ?? '',
      platform: json['platform'] ?? 'Unknown',
      sourceUrl: json['source_url'] ?? '',
      video: VideoStreamInfo.fromJson(
        json['video'] ?? {},
      ),
      audio: AudioStreamInfo.fromJson(
        json['audio'] ?? {},
      ),
      availableFormats:
          List<String>.from(
        json['available_formats'] ?? [],
      ),
    );
  }
}


class VideoStreamInfo {
  final String url;
  final String formatId;
  final String extension;

  final int? width;
  final int? height;

  final String? resolution;

  VideoStreamInfo({
    required this.url,
    required this.formatId,
    required this.extension,
    this.width,
    this.height,
    this.resolution,
  });

  factory VideoStreamInfo.fromJson(
    Map<String, dynamic> json,
  ) {
    return VideoStreamInfo(
      url: json['url'] ?? '',
      formatId: json['format_id'] ?? '',
      extension: json['extension'] ?? 'mp4',
      width: json['width'],
      height: json['height'],
      resolution: json['resolution'],
    );
  }
}


class AudioStreamInfo {
  final String url;
  final String formatId;
  final String extension;

  final double? abr;

  AudioStreamInfo({
    required this.url,
    required this.formatId,
    required this.extension,
    this.abr,
  });

  factory AudioStreamInfo.fromJson(
    Map<String, dynamic> json,
  ) {
    return AudioStreamInfo(
      url: json['url'] ?? '',
      formatId: json['format_id'] ?? '',
      extension: json['extension'] ?? 'm4a',
      abr: json['abr'] != null
          ? (json['abr'] as num).toDouble()
          : null,
    );
  }
}