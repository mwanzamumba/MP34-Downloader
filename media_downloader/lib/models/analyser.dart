class MediaInfo {
  final String title;
  final String thumbnail;
  final String platform;
  final String sourceUrl;

  MediaInfo({
    required this.title,
    required this.thumbnail,
    required this.platform,
    required this.sourceUrl,
  });

  factory MediaInfo.fromJson(Map<String, dynamic> json) {
    return MediaInfo(
      title: json['title'] as String? ?? 'Untitled media',
      thumbnail: json['thumbnail'] as String? ?? '',
      platform: json['platform'] as String? ?? 'Other',
      sourceUrl: json['source_url'] as String? ?? '',
    );
  }
}
