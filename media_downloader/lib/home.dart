import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../models/analyser.dart';
import '../services/media_api.dart';

class Homepage extends StatefulWidget {
  const Homepage({
    super.key,
    required this.username,
  });

  final String username;

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

  double _downloadProgress = 0;

  String? _errorMessage;
  String? _downloadedFileName;
  String? _downloadLocation;

  @override
  void dispose() {
    _urlController.dispose();

    _downloadCancelToken?.cancel(
      'Page disposed',
    );

    super.dispose();
  }

  // ==========================================================
  // ANALYZE
  // ==========================================================

  Future<void> _analyzeMedia() async {
    FocusScope.of(context).unfocus();

    final url = _urlController.text.trim();

    if (url.isEmpty) {
      _showMessage(
        'Paste a media link first.',
      );
      return;
    }

    setState(() {
      _isAnalyzing = true;
      _errorMessage = null;
      _media = null;
      _downloadedFileName = null;
      _downloadLocation = null;
      _downloadProgress = 0;
    });

    try {
      final result = await _mediaApi.analyse(url);

      if (!mounted) {
        return;
      }

      setState(() {
        _media = result;
      });
    } on MediaApiException catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _errorMessage = error.message;
      });

      _showMessage(
        error.message,
      );
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _errorMessage = error.toString();
      });

      _showMessage(
        'Could not analyze this link.',
      );
    } finally {
      if (mounted) {
        setState(() {
          _isAnalyzing = false;
        });
      }
    }
  }

  // ==========================================================
  // DOWNLOAD
  // ==========================================================

  Future<void> _downloadMedia() async {
    if (_media == null) {
      _showMessage(
        'Analyze the link before downloading.',
      );
      return;
    }

    if (_isDownloading) {
      return;
    }

    final sourceUrl = _media!.sourceUrl;

    if (sourceUrl.trim().isEmpty) {
      _showMessage(
        'No source URL was returned by the server.',
      );
      return;
    }

    final title = _media!.title;

    _downloadCancelToken = CancelToken();

    setState(() {
      _isDownloading = true;
      _isPaused = false;
      _downloadProgress = 0;
      _errorMessage = null;
      _downloadedFileName = null;
      _downloadLocation = null;
    });

    try {
      final result = await _mediaApi.download(
        sourceUrl,
        title: title,
        cancelToken: _downloadCancelToken,
        onProgress: (received, total) {
          if (!mounted) {
            return;
          }

          if (total > 0) {
            setState(() {
              _downloadProgress =
                  (received / total).clamp(0.0, 1.0);
            });
          }
        },
      );

      if (!mounted) {
        return;
      }

      setState(() {
        _downloadProgress = 1;
        _downloadedFileName = result.fileName;
        _downloadLocation = result.location;
        _isDownloading = false;
        _isPaused = false;
      });

      _showMessage(
        'Download complete.',
      );
    } on DownloadCancelledException {
      if (!mounted) {
        return;
      }

      setState(() {
        _isDownloading = false;
      });
    } on MediaApiException catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isDownloading = false;
        _isPaused = false;
        _errorMessage = error.message;
      });

      _showMessage(
        error.message,
      );
    } catch (error) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isDownloading = false;
        _isPaused = false;
        _errorMessage = error.toString();
      });

      _showMessage(
        'Download failed.',
      );
    } finally {
      _downloadCancelToken = null;
    }
  }

  // ==========================================================
  // PAUSE
  // ==========================================================

  Future<void> _pauseDownload() async {
    if (!_isDownloading) {
      return;
    }

    setState(() {
      _isPaused = true;
    });

    _downloadCancelToken?.cancel(
      'Download paused',
    );
  }

  // ==========================================================
  // RESUME
  // ==========================================================

  Future<void> _resumeDownload() async {
    if (!_isPaused) {
      return;
    }

    setState(() {
      _isPaused = false;
    });

    // The current backend does not support HTTP range resume.
    // Therefore this starts the transfer again.
    await _downloadMedia();
  }

  // ==========================================================
  // CANCEL
  // ==========================================================

  Future<void> _cancelDownload() async {
    if (!_isDownloading && !_isPaused) {
      return;
    }

    _downloadCancelToken?.cancel(
      'Download cancelled by user',
    );

    if (!mounted) {
      return;
    }

    setState(() {
      _isDownloading = false;
      _isPaused = false;
      _downloadProgress = 0;
    });

    _showMessage(
      'Download cancelled.',
    );
  }

  // ==========================================================
  // MESSAGE
  // ==========================================================

  void _showMessage(String message) {
    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior: SnackBarBehavior.floating,
        ),
      );
  }

  // ==========================================================
  // BUILD
  // ==========================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F8FA),
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  20,
                  22,
                  20,
                  0,
                ),
                child: _buildHeader(),
              ),
            ),

            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  20,
                  24,
                  20,
                  0,
                ),
                child: _buildLinkSection(),
              ),
            ),

            if (_errorMessage != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    20,
                    14,
                    20,
                    0,
                  ),
                  child: _buildErrorCard(),
                ),
              ),

            if (_media != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    20,
                    18,
                    20,
                    0,
                  ),
                  child: _buildMediaCard(),
                ),
              ),

            if (_isDownloading || _isPaused)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    20,
                    18,
                    20,
                    0,
                  ),
                  child: _buildDownloadStatus(),
                ),
              ),

            if (_downloadedFileName != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    20,
                    18,
                    20,
                    0,
                  ),
                  child: _buildCompletedCard(),
                ),
              ),

            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  20,
                  24,
                  20,
                  30,
                ),
                child: _buildPremiumCard(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ==========================================================
  // HEADER
  // ==========================================================

  Widget _buildHeader() {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment:
                CrossAxisAlignment.start,
            children: [
              Text(
                'Hello, ${widget.username}',
                style: const TextStyle(
                  fontSize: 15,
                  color: Colors.black54,
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'Download media',
                style: TextStyle(
                  fontSize: 27,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(14),
          ),
          child: const Icon(
            Icons.download_rounded,
            color: Colors.white,
          ),
        ),
      ],
    );
  }

  // ==========================================================
  // LINK SECTION
  // ==========================================================

  Widget _buildLinkSection() {
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,
      children: [
        const Text(
          'Paste media link',
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w700,
          ),
        ),

        const SizedBox(height: 10),

        Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: const Color(0xFFE4E6EA),
            ),
          ),
          child: TextField(
            controller: _urlController,
            keyboardType: TextInputType.url,
            textInputAction: TextInputAction.done,
            decoration: const InputDecoration(
              hintText: 'https://...',
              prefixIcon: Icon(
                Icons.link_rounded,
              ),
              border: InputBorder.none,
              contentPadding: EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 16,
              ),
            ),
            onSubmitted: (_) {
              _analyzeMedia();
            },
          ),
        ),

        const SizedBox(height: 12),

        // IMPORTANT:
        // Analyze button is BELOW the TextField.
        SizedBox(
          width: double.infinity,
          height: 52,
          child: FilledButton.icon(
            onPressed:
                _isAnalyzing || _isDownloading
                    ? null
                    : _analyzeMedia,
            icon: Icon(
              _isAnalyzing
                  ? Icons.hourglass_top_rounded
                  : Icons.search_rounded,
            ),
            label: Text(
              _isAnalyzing
                  ? 'Analyzing...'
                  : 'Analyze',
              style: const TextStyle(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ],
    );
  }

  // ==========================================================
  // ERROR
  // ==========================================================

  Widget _buildErrorCard() {
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: Colors.red.withOpacity(0.07),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.red.withOpacity(0.2),
        ),
      ),
      child: Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.error_outline_rounded,
            color: Colors.red,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _errorMessage!,
              style: const TextStyle(
                color: Colors.red,
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ==========================================================
  // MEDIA CARD
  // ==========================================================

  Widget _buildMediaCard() {
    final media = _media!;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: const Color(0xFFE6E7EA),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          if (media.thumbnail.isNotEmpty)
            ClipRRect(
              borderRadius:
                  BorderRadius.circular(14),
              child: AspectRatio(
                aspectRatio: 16 / 9,
                child: Image.network(
                  media.thumbnail,
                  fit: BoxFit.cover,
                  errorBuilder:
                      (_, __, ___) {
                    return Container(
                      color:
                          const Color(0xFFF0F1F3),
                      child: const Icon(
                        Icons.video_library_outlined,
                        size: 42,
                        color: Colors.black38,
                      ),
                    );
                  },
                ),
              ),
            ),

          const SizedBox(height: 14),

          Text(
            media.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.w700,
            ),
          ),

          const SizedBox(height: 6),

          Text(
            media.platform,
            style: const TextStyle(
              color: Colors.black54,
            ),
          ),

          const SizedBox(height: 14),

          if (!_isDownloading && !_isPaused)
            SizedBox(
              width: double.infinity,
              height: 50,
              child: FilledButton.icon(
                onPressed: _downloadMedia,
                icon: const Icon(
                  Icons.download_rounded,
                ),
                label: const Text(
                  'Download',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),

          if (_isDownloading || _isPaused)
            _buildDownloadButtons(),
        ],
      ),
    );
  }

  // ==========================================================
  // DOWNLOAD BUTTONS
  // ==========================================================

  Widget _buildDownloadButtons() {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed:
                _isPaused
                    ? _resumeDownload
                    : _pauseDownload,
            icon: Icon(
              _isPaused
                  ? Icons.play_arrow_rounded
                  : Icons.pause_rounded,
            ),
            label: Text(
              _isPaused
                  ? 'Resume'
                  : 'Pause',
            ),
          ),
        ),

        const SizedBox(width: 10),

        Expanded(
          child: OutlinedButton.icon(
            onPressed: _cancelDownload,
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.red,
            ),
            icon: const Icon(
              Icons.close_rounded,
            ),
            label: const Text(
              'Cancel',
            ),
          ),
        ),
      ],
    );
  }

  // ==========================================================
  // DOWNLOAD STATUS
  // ==========================================================

  Widget _buildDownloadStatus() {
    final percentage =
        (_downloadProgress * 100)
            .round();

    return Container(
      padding: const EdgeInsets.all(17),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: const Color(0xFFE6E7EA),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.downloading_rounded,
              ),
              const SizedBox(width: 9),
              Expanded(
                child: Text(
                  _isPaused
                      ? 'Download paused'
                      : 'Downloading...',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                '$percentage%',
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),

          const SizedBox(height: 13),

          ClipRRect(
            borderRadius:
                BorderRadius.circular(10),
            child: LinearProgressIndicator(
              value: _downloadProgress,
              minHeight: 8,
            ),
          ),

          const SizedBox(height: 14),

          _buildDownloadButtons(),
        ],
      ),
    );
  }

  // ==========================================================
  // COMPLETED
  // ==========================================================

  Widget _buildCompletedCard() {
    return Container(
      padding: const EdgeInsets.all(17),
      decoration: BoxDecoration(
        color: Colors.green.withOpacity(0.07),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.green.withOpacity(0.2),
        ),
      ),
      child: Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.check_circle_rounded,
            color: Colors.green,
            size: 30,
          ),

          const SizedBox(width: 12),

          Expanded(
            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [
                const Text(
                  'Download complete',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),

                const SizedBox(height: 5),

                Text(
                  _downloadedFileName ??
                      'Media file',
                  maxLines: 2,
                  overflow:
                      TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.black87,
                  ),
                ),

                if (_downloadLocation != null)
                  Padding(
                    padding:
                        const EdgeInsets.only(
                      top: 5,
                    ),
                    child: Text(
                      _downloadLocation!,
                      style: const TextStyle(
                        color: Colors.black54,
                        fontSize: 13,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ==========================================================
  // PREMIUM
  // ==========================================================

  Widget _buildPremiumCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Row(
        children: [
          Icon(
            Icons.workspace_premium_rounded,
            color: Colors.amber,
            size: 35,
          ),
          SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [
                Text(
                  'MP34 Premium',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 5),
                Text(
                  'Faster downloads and more features.',
                  style: TextStyle(
                    color: Colors.white70,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}