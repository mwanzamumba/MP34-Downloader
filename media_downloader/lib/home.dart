import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../models/analyser.dart';
import '../services/media_api.dart';

class Homepage extends StatefulWidget {
  const Homepage({super.key});

  @override
  State<Homepage> createState() => _HomepageState();
}

class _HomepageState extends State<Homepage> {
  final TextEditingController _urlController =
      TextEditingController();

  final MediaApi _mediaApi = MediaApi();

  MediaInfo? _media;

  CancelToken? _downloadCancelToken;

  bool _isAnalyzing = false;
  bool _isDownloading = false;
  bool _isPaused = false;

  // Used to distinguish CANCEL from PAUSE.
  bool _cancelRequested = false;

  double _downloadProgress = 0;

  int _receivedBytes = 0;
  int _totalBytes = 0;

  String? _errorMessage;

  String? _downloadedFileName;
  String? _downloadLocation;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  // ============================================================
  // ANALYZE
  // ============================================================

  Future<void> _analyzeMedia() async {
    final url = _urlController.text.trim();

    if (url.isEmpty) {
      setState(() {
        _errorMessage = 'Please enter a media URL.';
      });
      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {
      _isAnalyzing = true;
      _errorMessage = null;
      _media = null;
      _downloadedFileName = null;
      _downloadLocation = null;
      _downloadProgress = 0;
      _receivedBytes = 0;
      _totalBytes = 0;
    });

    try {
      final media = await _mediaApi.analyse(url);

      if (!mounted) return;

      setState(() {
        _media = media;
        _isAnalyzing = false;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _isAnalyzing = false;
        _errorMessage = error.toString();
      });
    }
  }

  // ============================================================
  // START DOWNLOAD
  // ============================================================

  Future<void> _startDownload() async {
    final media = _media;

    if (media == null) {
      return;
    }

    // Prevent duplicate download requests.
    if (_isDownloading) {
      return;
    }

    setState(() {
      _isDownloading = true;
      _isPaused = false;
      _cancelRequested = false;
      _errorMessage = null;
    });

    final cancelToken = CancelToken();

    _downloadCancelToken = cancelToken;

    try {
      final result = await _mediaApi.download(
        media,
        cancelToken: cancelToken,
        onProgress: (received, total) {
          if (!mounted) return;

          setState(() {
            _receivedBytes = received;
            _totalBytes = total;

            if (total > 0) {
              _downloadProgress =
                  (received / total).clamp(0.0, 1.0);
            }
          });
        },
      );

      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _isPaused = false;
        _cancelRequested = false;
        _downloadProgress = 1.0;
        _downloadedFileName = result.fileName;
        _downloadLocation = result.location;
      });
    } on DownloadPausedException {
      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _isPaused = true;
      });

      await _mediaApi.showPaused(
        _media?.title ?? 'Download',
      );
    } on DownloadCancelledException {
      // --------------------------------------------------------
      // CANCEL:
      // Delete the partial file.
      // --------------------------------------------------------

      await _mediaApi.deletePartialDownload(media);

      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _isPaused = false;
        _cancelRequested = false;

        _downloadProgress = 0;
        _receivedBytes = 0;
        _totalBytes = 0;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _isPaused = false;
        _cancelRequested = false;
        _errorMessage = error.toString();
      });

      await _mediaApi.showFailed(
        error.toString(),
      );
    } finally {
      _downloadCancelToken = null;
    }
  }

  // ============================================================
  // PAUSE
  // ============================================================

  void _pauseDownload() {
    if (!_isDownloading) {
      return;
    }

    if (_downloadCancelToken == null) {
      return;
    }

    _cancelRequested = false;

    // IMPORTANT:
    // Do NOT delete the .part file.
    //
    // MediaApi will keep it so Resume can continue from
    // the existing number of bytes.
    _downloadCancelToken!.cancel('pause');
  }

  // ============================================================
  // RESUME
  // ============================================================

  Future<void> _resumeDownload() async {
    if (!_isPaused) {
      return;
    }

    if (_media == null) {
      return;
    }

    // ----------------------------------------------------------
    // IMPORTANT FIX:
    //
    // We MUST set _isDownloading to false before calling
    // _startDownload().
    //
    // Otherwise _startDownload() sees:
    //
    //     _isDownloading == true
    //
    // and immediately returns.
    //
    // This was the reason Resume could appear to do nothing.
    // ----------------------------------------------------------

    setState(() {
      _isPaused = false;
      _isDownloading = false;
      _errorMessage = null;
    });

    await _startDownload();
  }

  // ============================================================
  // CANCEL
  // ============================================================

  void _cancelDownload() {
    if (!_isDownloading) {
      return;
    }

    if (_downloadCancelToken == null) {
      return;
    }

    _cancelRequested = true;

    // IMPORTANT:
    // We don't delete the partial file here.
    //
    // We let MediaApi finish closing the file first.
    //
    // _startDownload() catches DownloadCancelledException
    // and then deletes the partial file safely.
    _downloadCancelToken!.cancel('cancel');
  }

  // ============================================================
  // CLEAR
  // ============================================================

  void _clearMedia() {
    setState(() {
      _media = null;
      _downloadedFileName = null;
      _downloadLocation = null;
      _errorMessage = null;

      _downloadProgress = 0;
      _receivedBytes = 0;
      _totalBytes = 0;

      _isDownloading = false;
      _isPaused = false;
      _cancelRequested = false;
    });

    _urlController.clear();
  }

  // ============================================================
  // PLATFORM ICON
  // ============================================================

  IconData _platformIcon(String platform) {
    final value = platform.toLowerCase();

    if (value.contains('youtube')) {
      return Icons.smart_display;
    }

    if (value.contains('facebook')) {
      return Icons.facebook;
    }

    if (value.contains('instagram')) {
      return Icons.camera_alt;
    }

    if (value.contains('tiktok')) {
      return Icons.music_note;
    }

    if (value.contains('twitter') ||
        value.contains('x /')) {
      return Icons.alternate_email;
    }

    return Icons.public;
  }

  // ============================================================
  // FORMAT BYTES
  // ============================================================

  String _formatBytes(int bytes) {
    if (bytes <= 0) {
      return '0 B';
    }

    const units = [
      'B',
      'KB',
      'MB',
      'GB',
    ];

    double size = bytes.toDouble();
    int unitIndex = 0;

    while (size >= 1024 &&
        unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }

    return '${size.toStringAsFixed(size >= 100 ? 0 : 1)} ${units[unitIndex]}';
  }

  // ============================================================
  // UI
  // ============================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F7FA),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        centerTitle: false,
        title: const Text(
          'MP34 Downloader',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            color: Colors.black87,
          ),
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Download your media',
                style: TextStyle(
                  fontSize: 25,
                  fontWeight: FontWeight.bold,
                ),
              ),

              const SizedBox(height: 6),

              const Text(
                'Paste a video or media link below to get started.',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.black54,
                ),
              ),

              const SizedBox(height: 22),

              // ------------------------------------------------
              // URL FIELD
              // ------------------------------------------------

              Container(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: [
                    BoxShadow(
                      blurRadius: 10,
                      spreadRadius: 1,
                      color: Colors.black.withOpacity(0.04),
                    ),
                  ],
                ),
                child: TextField(
                  controller: _urlController,
                  keyboardType: TextInputType.url,
                  decoration: InputDecoration(
                    hintText: 'Paste media URL',
                    prefixIcon: const Icon(
                      Icons.link,
                    ),
                    suffixIcon: Padding(
                      padding: const EdgeInsets.all(6),
                      child: ElevatedButton(
                        onPressed:
                            _isAnalyzing || _isDownloading
                                ? null
                                : _analyzeMedia,
                        style: ElevatedButton.styleFrom(
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(10),
                          ),
                        ),
                        child: _isAnalyzing
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child:
                                    CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text('Analyze'),
                      ),
                    ),
                    border: InputBorder.none,
                    contentPadding:
                        const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 17,
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // ------------------------------------------------
              // ERROR
              // ------------------------------------------------

              if (_errorMessage != null)
                Container(
                  width: double.infinity,
                  margin:
                      const EdgeInsets.only(bottom: 16),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.red.shade50,
                    borderRadius:
                        BorderRadius.circular(12),
                    border: Border.all(
                      color: Colors.red.shade100,
                    ),
                  ),
                  child: Row(
                    crossAxisAlignment:
                        CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.error_outline,
                        color: Colors.red.shade700,
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _errorMessage!,
                          style: TextStyle(
                            color: Colors.red.shade800,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),

              // ------------------------------------------------
              // MEDIA CARD
              // ------------------------------------------------

              if (_media != null)
                _buildMediaCard(),

              // ------------------------------------------------
              // DOWNLOAD PROGRESS
              // ------------------------------------------------

              if (_isDownloading || _isPaused)
                _buildProgressCard(),

              // ------------------------------------------------
              // COMPLETE
              // ------------------------------------------------

              if (_downloadedFileName != null)
                _buildCompleteCard(),
            ],
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
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            blurRadius: 12,
            spreadRadius: 1,
            color: Colors.black.withOpacity(0.04),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          if (media.thumbnail.isNotEmpty)
            ClipRRect(
              borderRadius:
                  BorderRadius.circular(12),
              child: AspectRatio(
                aspectRatio: 16 / 9,
                child: Image.network(
                  media.thumbnail,
                  fit: BoxFit.cover,
                  errorBuilder:
                      (_, __, ___) {
                    return Container(
                      color: Colors.grey.shade200,
                      child: const Center(
                        child: Icon(
                          Icons.image_not_supported,
                          size: 45,
                          color: Colors.grey,
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),

          const SizedBox(height: 14),

          Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius:
                      BorderRadius.circular(12),
                ),
                child: Icon(
                  _platformIcon(media.platform),
                  color: Colors.blue.shade700,
                ),
              ),

              const SizedBox(width: 12),

              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    Text(
                      media.title,
                      maxLines: 2,
                      overflow:
                          TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      media.platform,
                      style: TextStyle(
                        color: Colors.grey.shade600,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 16),

          if (!_isDownloading &&
              !_isPaused &&
              _downloadedFileName == null)
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton.icon(
                onPressed: _startDownload,
                icon: const Icon(
                  Icons.download_rounded,
                ),
                label: const Text(
                  'Download',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                style: ElevatedButton.styleFrom(
                  shape: RoundedRectangleBorder(
                    borderRadius:
                        BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  // ============================================================
  // PROGRESS CARD
  // ============================================================

  Widget _buildProgressCard() {
    final percent =
        (_downloadProgress * 100).round();

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius:
            BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            blurRadius: 12,
            spreadRadius: 1,
            color: Colors.black.withOpacity(0.04),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.download_rounded,
                color: Colors.blue,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _isPaused
                      ? 'Download paused'
                      : 'Downloading...',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Text(
                '$percent%',
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),

          const SizedBox(height: 14),

          ClipRRect(
            borderRadius:
                BorderRadius.circular(20),
            child: LinearProgressIndicator(
              value: _totalBytes > 0
                  ? _downloadProgress
                  : null,
              minHeight: 8,
            ),
          ),

          const SizedBox(height: 10),

          if (_totalBytes > 0)
            Text(
              '${_formatBytes(_receivedBytes)} / ${_formatBytes(_totalBytes)}',
              style: TextStyle(
                color: Colors.grey.shade600,
                fontSize: 13,
              ),
            )
          else
            Text(
              _formatBytes(_receivedBytes),
              style: TextStyle(
                color: Colors.grey.shade600,
                fontSize: 13,
              ),
            ),

          const SizedBox(height: 16),

          // ----------------------------------------------------
          // ONLY ONE PAUSE/RESUME + ONE CANCEL
          // ----------------------------------------------------

          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isPaused
                      ? _resumeDownload
                      : _pauseDownload,
                  icon: Icon(
                    _isPaused
                        ? Icons.play_arrow
                        : Icons.pause,
                  ),
                  label: Text(
                    _isPaused
                        ? 'Resume'
                        : 'Pause',
                  ),
                  style: OutlinedButton.styleFrom(
                    minimumSize:
                        const Size.fromHeight(46),
                    shape: RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(10),
                    ),
                  ),
                ),
              ),

              const SizedBox(width: 10),

              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isDownloading
                      ? _cancelDownload
                      : null,
                  icon: const Icon(
                    Icons.close,
                  ),
                  label: const Text(
                    'Cancel',
                  ),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.red,
                    side: const BorderSide(
                      color: Colors.red,
                    ),
                    minimumSize:
                        const Size.fromHeight(46),
                    shape: RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(10),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ============================================================
  // COMPLETE CARD
  // ============================================================

  Widget _buildCompleteCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.green.shade50,
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color: Colors.green.shade100,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: Colors.green.shade100,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.check,
                  color: Colors.green.shade700,
                ),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Text(
                  'Download complete',
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: 14),

          Text(
            _downloadedFileName ?? '',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontWeight: FontWeight.w600,
            ),
          ),

          const SizedBox(height: 6),

          Text(
            _downloadLocation ?? '',
            style: TextStyle(
              color: Colors.grey.shade700,
              fontSize: 13,
            ),
          ),

          const SizedBox(height: 16),

          SizedBox(
            width: double.infinity,
            height: 46,
            child: OutlinedButton.icon(
              onPressed: _clearMedia,
              icon: const Icon(
                Icons.add,
              ),
              label: const Text(
                'Download Another',
              ),
              style: OutlinedButton.styleFrom(
                shape: RoundedRectangleBorder(
                  borderRadius:
                      BorderRadius.circular(10),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}