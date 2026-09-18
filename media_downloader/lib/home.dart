import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '../models/analyser.dart';
import '../services/media_api.dart';
import '../services/download_service.dart';

class Homepage extends StatefulWidget {
  const Homepage({super.key});

  @override
  State<Homepage> createState() => _HomepageState();
}

class _HomepageState extends State<Homepage> {
  final TextEditingController _urlController = TextEditingController();

  final MediaApi _api = MediaApi();

  // Keep the concrete analysis model supplied by MediaApi.
  MediaInfo? _media;

  bool _analysing = false;
  bool _downloading = false;

  // This is the UI selection.
  // The actual yt-dlp format_id is obtained from the backend.
  String _selectedFormat = 'mp4';

  double _progress = 0;

  String _status = '';

  CancelToken? _cancelToken;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  // ============================================================
  // ANALYSE
  // ============================================================

  Future<void> _analyze() async {
    final url = _urlController.text.trim();

    if (url.isEmpty) {
      _showMessage('Please enter a media URL.');
      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {
      _analysing = true;
      _media = null;
      _status = 'Analysing link...';
    });

    try {
      final result = await _api.analyse(url);

      if (!mounted) return;

      setState(() {
        _media = result;
        _status = 'Ready to download';
      });

      // Automatically select MP4 when a video format exists.
      if (_getVideoFormat() != null) {
        setState(() {
          _selectedFormat = 'mp4';
        });
      } else if (_getAudioFormat() != null) {
        setState(() {
          _selectedFormat = 'mp3';
        });
      }
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _status = '';
      });

      _showMessage(_cleanError(e));
    } finally {
      if (mounted) {
        setState(() {
          _analysing = false;
        });
      }
    }
  }

  // ============================================================
  // GET REAL VIDEO FORMAT
  // ============================================================

  MediaFormat? _getVideoFormat() {
    final media = _media;

    if (media == null) {
      return null;
    }

    // First use the backend's recommended format.
    if (media.recommendedVideo != null) {
      return media.recommendedVideo;
    }

    // Then progressive formats.
    if (media.progressiveFormats.isNotEmpty) {
      return media.progressiveFormats.first;
    }

    // Finally video-only formats.
    if (media.videoFormats.isNotEmpty) {
      return media.videoFormats.first;
    }

    return null;
  }

  // ============================================================
  // GET REAL AUDIO FORMAT
  // ============================================================

  MediaFormat? _getAudioFormat() {
    final media = _media;

    if (media == null) {
      return null;
    }

    if (media.recommendedAudio != null) {
      return media.recommendedAudio;
    }

    if (media.audioFormats.isNotEmpty) {
      return media.audioFormats.first;
    }

    // If YouTube only supplied a progressive format,
    // the backend can extract audio from that format.
    if (media.progressiveFormats.isNotEmpty) {
      return media.progressiveFormats.first;
    }

    return null;
  }

  // ============================================================
  // GET SELECTED REAL FORMAT
  // ============================================================

  MediaFormat? _getSelectedMediaFormat() {
    if (_selectedFormat == 'mp4') {
      return _getVideoFormat();
    }

    return _getAudioFormat();
  }

  // ============================================================
  // DOWNLOAD
  // ============================================================

  Future<void> _download() async {
    final media = _media;

    if (media == null) {
      _showMessage('Analyse a link first.');
      return;
    }

    final selectedMediaFormat = _getSelectedMediaFormat();

    if (selectedMediaFormat == null) {
      _showMessage(
        _selectedFormat == 'mp4'
            ? 'No video format is available for this media.'
            : 'No audio format is available for this media.',
      );
      return;
    }

    /*
     * IMPORTANT:
     *
     * selectedMediaFormat.formatId is the REAL yt-dlp format ID.
     *
     * Example:
     *
     * Flutter selection: MP4
     * Backend format_id: 18
     *
     * We do NOT guess the format ID.
     */

    _cancelToken = CancelToken();

    setState(() {
      _downloading = true;
      _progress = 0;
      _status = 'Preparing download...';
    });

    try {
      /*
       * The current DownloadService handles the actual file
       * download/storage process.
       *
       * We pass the REAL format ID instead of simply passing
       * "mp4" or "mp3".
       */
      await DownloadService.download(
        media: media,
        sourceUrl: _urlController.text.trim(),
        format: selectedMediaFormat.formatId,
        cancelToken: _cancelToken!,
        onProgress: (value, status) {
          if (!mounted) return;

          setState(() {
            _progress = value;
            _status = status;
          });
        },
      );

      if (!mounted) return;

      setState(() {
        _progress = 1;
        _status = 'Download complete';
      });

      _showMessage(
        _selectedFormat == 'mp4'
            ? 'MP4 saved successfully.'
            : 'MP3 saved successfully.',
      );
    } catch (e) {
      if (!mounted) return;

      if (e is DioException && CancelToken.isCancel(e)) {
        setState(() {
          _status = 'Download cancelled';
        });

        _showMessage('Download cancelled.');
      } else {
        setState(() {
          _status = 'Download failed';
        });

        _showMessage(_cleanError(e));
      }
    } finally {
      _cancelToken = null;

      if (mounted) {
        setState(() {
          _downloading = false;
        });
      }
    }
  }

  void _cancelDownload() {
    _cancelToken?.cancel('Download cancelled by user');
  }

  // ============================================================
  // CLEAR URL
  // ============================================================

  void _clearUrl() {
    if (_downloading) return;

    setState(() {
      _urlController.clear();
      _media = null;
      _status = '';
      _progress = 0;
    });
  }

  // ============================================================
  // SOCIAL LINKS
  // ============================================================

  Future<void> _openSocial(String url) async {
    final uri = Uri.parse(url);

    try {
      final launched = await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      );

      if (!launched) {
        _showMessage('Could not open this application.');
      }
    } catch (_) {
      _showMessage('Could not open this application.');
    }
  }

  // ============================================================
  // ERROR HANDLING
  // ============================================================

  String _cleanError(Object error) {
    if (error is DioException) {
      if (error.response?.data is Map) {
        final data = error.response!.data as Map;

        if (data['detail'] != null) {
          return data['detail'].toString();
        }

        if (data['error'] != null) {
          return data['error'].toString();
        }
      }

      return error.message ?? 'Network error.';
    }

    return error.toString().replaceFirst('Exception: ', '');
  }

  // ============================================================
  // MESSAGE
  // ============================================================

  void _showMessage(String message) {
    if (!mounted) return;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior: SnackBarBehavior.floating,
        ),
      );
  }

  // ============================================================
  // BUILD
  // ============================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8F7FC),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 30),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildTopHeader(),

              const SizedBox(height: 22),

              _buildUrlInput(),

              const SizedBox(height: 12),

              _buildSocialSection(),

              const SizedBox(height: 18),

              _buildAnalyzeButton(),

              const SizedBox(height: 24),

              if (_media != null) ...[
                _buildMediaCard(),

                const SizedBox(height: 22),

                _buildFormatSelector(),

                const SizedBox(height: 20),

                _buildDownloadArea(),
              ],

              if (_status.isNotEmpty && _media == null) ...[
                const SizedBox(height: 12),
                Center(
                  child: Text(
                    _status,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey.shade600,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  // ============================================================
  // HEADER
  // ============================================================

  Widget _buildTopHeader() {
    return Row(
      children: [
        Container(
          width: 46,
          height: 46,
            padding: const EdgeInsets.all(8),
            child: Image.asset(
              'lib/asset/mp34-logo.png',
              fit: BoxFit.contain,
            ),
          ),

        const SizedBox(width: 12),

        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'MP34 Downloader',
                style: TextStyle(
                  fontSize: 21,
                  fontWeight: FontWeight.bold,
                ),
              ),

              const SizedBox(height: 3),

              Text(
                'Download media from your favourite platforms',
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey.shade600,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // ============================================================
  // URL INPUT
  // ============================================================

  Widget _buildUrlInput() {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.grey.shade200,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: TextField(
        controller: _urlController,
        enabled: !_downloading,
        keyboardType: TextInputType.url,
        textInputAction: TextInputAction.done,
        onChanged: (_) {
          setState(() {});
        },
        onSubmitted: (_) => _analyze(),
        decoration: InputDecoration(
          hintText: 'Paste your link here',
          hintStyle: TextStyle(
            color: Colors.grey.shade500,
          ),

          prefixIcon: Icon(
            Icons.link_rounded,
            color: Colors.grey.shade600,
          ),

          suffixIcon: _urlController.text.isNotEmpty
              ? IconButton(
                  tooltip: 'Clear',
                  onPressed: _clearUrl,
                  icon: const Icon(
                    Icons.close_rounded,
                  ),
                )
              : null,

          border: InputBorder.none,

          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 17,
          ),
        ),
      ),
    );
  }

  // ============================================================
  // SOCIAL SECTION
  // ============================================================

  Widget _buildSocialSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Center(
          child: Text(
            'Open Social App to Copy Link',
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey.shade600,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),

        const SizedBox(height: 14),

        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _socialButton(
              icon: FontAwesomeIcons.tiktok,
              label: 'TikTok',
              url: 'https://www.tiktok.com/',
            ),

            _socialButton(
              icon: FontAwesomeIcons.instagram,
              label: 'Instagram',
              url: 'https://www.instagram.com/',
            ),

            _socialButton(
              icon: FontAwesomeIcons.facebook,
              label: 'Facebook',
              url: 'https://www.facebook.com/',
            ),

            _socialButton(
              icon: FontAwesomeIcons.xTwitter,
              label: 'X',
              url: 'https://x.com/',
            ),

            _socialButton(
              icon: FontAwesomeIcons.youtube,
              label: 'YouTube',
              url: 'https://www.youtube.com/',
            ),
          ],
        ),
      ],
    );
  }

  Widget _socialButton({
    required dynamic icon,
    required String label,
    required String url,
  }) {
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: () => _openSocial(url),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: 7,
          vertical: 5,
        ),
        child: Column(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(15),
                border: Border.all(
                  color: Colors.grey.shade200,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 7,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: Center(
                child: FaIcon(
                  icon,
                  size: 22,
                  color: Colors.black87,
                ),
              ),
            ),

            const SizedBox(height: 6),

            Text(
              label,
              style: TextStyle(
                fontSize: 10,
                color: Colors.grey.shade700,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ============================================================
  // ANALYSE BUTTON
  // ============================================================

  Widget _buildAnalyzeButton() {
    return SizedBox(
      width: double.infinity,
      height: 52,
      child: ElevatedButton.icon(
        onPressed: _analysing || _downloading
            ? null
            : _analyze,
        icon: _analysing
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : const Icon(
                Icons.search_rounded,
              ),
        label: Text(
          _analysing
              ? 'Analysing...'
              : 'Analyse Link',
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.deepPurple,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),
    );
  }

  // ============================================================
  // MEDIA CARD
  // ============================================================

  Widget _buildMediaCard() {
    final media = _media!;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.grey.shade200,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildThumbnail(media.thumbnail ?? ''),

          const SizedBox(width: 14),

          Expanded(
            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [
                Text(
                  media.title,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),

                const SizedBox(height: 8),

                Row(
                  children: [
                    const Icon(
                      Icons.public,
                      size: 16,
                    ),
                    const SizedBox(width: 5),
                    Text(
                      media.platform,
                      style: TextStyle(
                        color: Colors.grey.shade700,
                      ),
                    ),
                  ],
                ),

              ],
            ),
          ),
        ],
      ),
    );
  }

  // ============================================================
  // THUMBNAIL
  // ============================================================

  Widget _buildThumbnail(String url) {
    if (url.isEmpty) {
      return Container(
        width: 100,
        height: 100,
        decoration: BoxDecoration(
          color: Colors.grey.shade200,
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Icon(
          Icons.video_library_outlined,
          size: 35,
        ),
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: Image.network(
        url,
        width: 100,
        height: 100,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) {
          return Container(
            width: 100,
            height: 100,
            color: Colors.grey.shade200,
            child: const Icon(
              Icons.video_library_outlined,
            ),
          );
        },
      ),
    );
  }

  // ============================================================
  // FORMAT SELECTOR
  // ============================================================

  Widget _buildFormatSelector() {
    final videoAvailable = _getVideoFormat() != null;
    final audioAvailable = _getAudioFormat() != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Choose format',
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.bold,
          ),
        ),

        const SizedBox(height: 12),

        Row(
          children: [
            Expanded(
              child: _formatCard(
                format: 'mp4',
                title: 'MP4',
                subtitle: videoAvailable
                    ? _getVideoSubtitle()
                    : 'Not available',
                icon: Icons.video_file_outlined,
                enabled: videoAvailable,
              ),
            ),

            const SizedBox(width: 12),

            Expanded(
              child: _formatCard(
                format: 'mp3',
                title: 'MP3',
                subtitle: audioAvailable
                    ? 'Audio only'
                    : 'Not available',
                icon: Icons.audio_file_outlined,
                enabled: audioAvailable,
              ),
            ),
          ],
        ),
      ],
    );
  }

  String _getVideoSubtitle() {
    final format = _getVideoFormat();

    if (format == null) {
      return 'Not available';
    }

    final quality = format.formatNote ??
      (format.height != null
        ? '${format.height}p'
        : 'Video');

    final extension = format.ext;
    return extension == null
      ? quality
      : '$quality • ${extension.toUpperCase()}';
  }

  Widget _formatCard({
    required String format,
    required String title,
    required String subtitle,
    required IconData icon,
    required bool enabled,
  }) {
    final selected =
        _selectedFormat == format && enabled;

    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: _downloading || !enabled
          ? null
          : () {
              setState(() {
                _selectedFormat = format;
              });
            },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: !enabled
              ? Colors.grey.shade100
              : selected
                  ? Colors.deepPurple.withValues(
                      alpha: 0.08,
                    )
                  : Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: !enabled
                ? Colors.grey.shade200
                : selected
                    ? Colors.deepPurple
                    : Colors.grey.shade200,
            width: selected ? 2 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,
          children: [
            Icon(
              icon,
              size: 30,
              color: !enabled
                  ? Colors.grey.shade400
                  : selected
                      ? Colors.deepPurple
                      : Colors.grey.shade700,
            ),

            const SizedBox(height: 10),

            Text(
              title,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 17,
                color: !enabled
                    ? Colors.grey.shade400
                    : Colors.black87,
              ),
            ),

            const SizedBox(height: 3),

            Text(
              subtitle,
              style: TextStyle(
                fontSize: 12,
                color: !enabled
                    ? Colors.grey.shade400
                    : Colors.grey.shade600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ============================================================
  // DOWNLOAD AREA
  // ============================================================

  Widget _buildDownloadArea() {
    if (!_downloading) {
      final selectedFormat =
          _getSelectedMediaFormat();

      final bool available =
          selectedFormat != null;

      return SizedBox(
        width: double.infinity,
        height: 54,
        child: ElevatedButton.icon(
          onPressed: available ? _download : null,
          icon: const Icon(
            Icons.file_download_outlined,
          ),
          label: Text(
            available
                ? 'Download ${_selectedFormat.toUpperCase()}'
                : 'Format not available',
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.deepPurple,
            foregroundColor: Colors.white,
            disabledBackgroundColor:
                Colors.grey.shade300,
            disabledForegroundColor:
                Colors.grey.shade600,
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
          ),
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.grey.shade200,
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  _status,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),

              Text(
                '${(_progress * 100).round()}%',
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          LinearProgressIndicator(
            value: _progress,
            minHeight: 7,
            borderRadius: BorderRadius.circular(10),
          ),

          const SizedBox(height: 16),

          SizedBox(
            width: double.infinity,
            height: 46,
            child: OutlinedButton.icon(
              onPressed: _cancelDownload,
              icon: const Icon(
                Icons.close,
              ),
              label: const Text(
                'Cancel',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
