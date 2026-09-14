class MediaInfo {
  final String title;
  final String thumbnail;
  final String platform;
  final String sourceUrl;
  final String downloadUrl;
  final String extension;
  final bool supportsResume;

  MediaInfo({
    required this.title,
    required this.thumbnail,
    required this.platform,
    required this.sourceUrl,
    required this.downloadUrl,
    required this.extension,
    required this.supportsResume,
  });

  factory MediaInfo.fromJson(Map<String, dynamic> json) {
    return MediaInfo(
      title: json['title'] as String? ?? 'Untitled media',
      thumbnail: json['thumbnail'] as String? ?? '',
      platform: json['platform'] as String? ?? 'Other',
      sourceUrl: json['source_url'] as String? ?? '',
      downloadUrl: json['download_url'] as String? ?? '',
      extension: json['extension'] as String? ?? 'mp4',
      supportsResume: json['supports_resume'] as bool? ?? false,
    );
  }
}