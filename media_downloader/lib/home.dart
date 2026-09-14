import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../models/analyser.dart';
import '../services/media_api.dart';

class Homepage extends StatefulWidget {
  const Homepage({super.key});

  @override
  State<Homepage> createState() =>
      _HomepageState();
}

class _HomepageState extends State<Homepage> {
  final TextEditingController _urlController =
      TextEditingController();

  final MediaApi _api = MediaApi.instance;

  MediaInfo? _media;

  CancelToken? _cancelToken;

  double _progress = 0.0;

  bool _isAnalyzing = false;
  bool _isDownloading = false;
  bool _downloadComplete = false;

  String? _savedFileName;
  String? _errorMessage;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  // ============================================================
  // ANALYZE
  // ============================================================

  Future<void> _analyze() async {
    final url = _urlController.text.trim();

    if (url.isEmpty) {
      _showError('Please enter a media URL.');
      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {
      _isAnalyzing = true;
      _downloadComplete = false;
      _savedFileName = null;
      _errorMessage = null;
      _media = null;
    });

    try {
      final media =
          await _api.analyze(url);

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
  // DOWNLOAD
  // ============================================================

  Future<void> _download() async {
    final media = _media;

    if (media == null) {
      return;
    }

    FocusScope.of(context).unfocus();

    _cancelToken = CancelToken();

    setState(() {
      _isDownloading = true;
      _downloadComplete = false;
      _progress = 0.0;
      _savedFileName = null;
      _errorMessage = null;
    });

    try {
      final savedPath =
          await _api.download(
        media,
        cancelToken: _cancelToken,
        onProgress: (progress) {
          if (!mounted) return;

          setState(() {
            _progress = progress;
          });
        },
      );

      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _downloadComplete = true;
        _progress = 1.0;
        _savedFileName = savedPath;
      });
    } on DownloadCancelledException {
      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _progress = 0.0;
      });
    } on MediaApiException catch (error) {
      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _progress = 0.0;
        _errorMessage = error.message;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _isDownloading = false;
        _progress = 0.0;
        _errorMessage =
            'Download failed: $error';
      });
    } finally {
      _cancelToken = null;
    }
  }

  // ============================================================
  // CANCEL
  // ============================================================

  void _cancelDownload() {
    if (_cancelToken != null &&
        !_cancelToken!.isCancelled) {
      _cancelToken!.cancel();
    }
  }

  // ============================================================
  // ERROR
  // ============================================================

  void _showError(String message) {
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
    final theme =
        Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'MP34 Downloader',
          style: TextStyle(
            fontWeight: FontWeight.bold,
          ),
        ),
        centerTitle: true,
      ),

      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment:
                CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 10),

              // ------------------------------------------------
              // HEADER
              // ------------------------------------------------

              Icon(
                Icons.download_rounded,
                size: 64,
                color:
                    theme.colorScheme.primary,
              ),

              const SizedBox(height: 12),

              Text(
                'Download Media',
                textAlign: TextAlign.center,
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),

              const SizedBox(height: 6),

              Text(
                'Paste a media link below to analyse and download it.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: Colors.grey.shade600,
                ),
              ),

              const SizedBox(height: 24),

              // ------------------------------------------------
              // URL FIELD
              // ------------------------------------------------

              TextField(
                controller: _urlController,
                keyboardType:
                    TextInputType.url,
                enabled:
                    !_isAnalyzing &&
                    !_isDownloading,
                decoration:
                    InputDecoration(
                  labelText:
                      'Media URL',
                  hintText:
                      'https://...',
                  prefixIcon:
                      const Icon(
                    Icons.link,
                  ),
                  suffixIcon:
                      _urlController.text
                              .isNotEmpty
                          ? IconButton(
                              icon:
                                  const Icon(
                                Icons.clear,
                              ),
                              onPressed:
                                  () {
                                _urlController
                                    .clear();

                                setState(
                                  () {},
                                );
                              },
                            )
                          : null,
                  border:
                      OutlineInputBorder(
                    borderRadius:
                        BorderRadius.circular(
                      16,
                    ),
                  ),
                ),
                onChanged: (_) {
                  setState(() {});
                },
              ),

              const SizedBox(height: 14),

              // ------------------------------------------------
              // ANALYZE BUTTON
              // ------------------------------------------------

              SizedBox(
                height: 52,
                child: FilledButton.icon(
                  onPressed:
                      (_isAnalyzing ||
                              _isDownloading)
                          ? null
                          : _analyze,
                  icon: _isAnalyzing
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child:
                              CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(
                          Icons.search,
                        ),
                  label: Text(
                    _isAnalyzing
                        ? 'Analysing...'
                        : 'Analyse Link',
                  ),
                ),
              ),

              // ------------------------------------------------
              // ERROR
              // ------------------------------------------------

              if (_errorMessage != null) ...[
                const SizedBox(height: 18),

                Container(
                  padding:
                      const EdgeInsets.all(14),
                  decoration:
                      BoxDecoration(
                    borderRadius:
                        BorderRadius.circular(
                      14,
                    ),
                    color:
                        Colors.red.withOpacity(
                      0.08,
                    ),
                    border:
                        Border.all(
                      color:
                          Colors.red.withOpacity(
                        0.3,
                      ),
                    ),
                  ),
                  child: Row(
                    crossAxisAlignment:
                        CrossAxisAlignment.start,
                    children: [
                      const Icon(
                        Icons.error_outline,
                        color: Colors.red,
                      ),
                      const SizedBox(
                        width: 10,
                      ),
                      Expanded(
                        child: Text(
                          _errorMessage!,
                          style:
                              const TextStyle(
                            color: Colors.red,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // ------------------------------------------------
              // MEDIA INFORMATION
              // ------------------------------------------------

              if (_media != null) ...[
                const SizedBox(height: 24),

                _buildMediaCard(
                  _media!,
                ),
              ],

              // ------------------------------------------------
              // DOWNLOAD PROGRESS
              // ------------------------------------------------

              if (_isDownloading) ...[
                const SizedBox(height: 20),

                _buildProgressCard(),
              ],

              // ------------------------------------------------
              // COMPLETE
              // ------------------------------------------------

              if (_downloadComplete) ...[
                const SizedBox(height: 20),

                _buildCompleteCard(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  // ============================================================
  // MEDIA CARD
  // ============================================================

  Widget _buildMediaCard(
    MediaInfo media,
  ) {
    return Card(
      elevation: 2,
      clipBehavior:
          Clip.antiAlias,
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          if (media.thumbnail.isNotEmpty)
            SizedBox(
              height: 210,
              width: double.infinity,
              child: Image.network(
                media.thumbnail,
                fit: BoxFit.cover,
                errorBuilder:
                    (
                  context,
                  error,
                  stackTrace,
                ) {
                  return Container(
                    color:
                        Colors.grey.shade200,
                    child: const Center(
                      child: Icon(
                        Icons
                            .image_not_supported_outlined,
                        size: 50,
                      ),
                    ),
                  );
                },
                loadingBuilder:
                    (
                  context,
                  child,
                  loadingProgress,
                ) {
                  if (loadingProgress ==
                      null) {
                    return child;
                  }

                  return const Center(
                    child:
                        CircularProgressIndicator(),
                  );
                },
              ),
            ),

          Padding(
            padding:
                const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [
                Text(
                  media.title,
                  maxLines: 3,
                  overflow:
                      TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),

                const SizedBox(height: 8),

                Row(
                  children: [
                    const Icon(
                      Icons.public,
                      size: 18,
                    ),
                    const SizedBox(
                      width: 6,
                    ),
                    Text(
                      media.platform,
                      style:
                          TextStyle(
                        color: Colors
                            .grey.shade700,
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 16),

                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: FilledButton.icon(
                    onPressed:
                        _isDownloading
                            ? null
                            : _download,
                    icon: const Icon(
                      Icons.download_rounded,
                    ),
                    label: const Text(
                      'Download',
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

  // ============================================================
  // PROGRESS CARD
  // ============================================================

  Widget _buildProgressCard() {
    final percentage =
        (_progress * 100)
            .clamp(0, 99.5);

    return Card(
      child: Padding(
        padding:
            const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.downloading_rounded,
                ),
                const SizedBox(
                  width: 10,
                ),
                const Expanded(
                  child: Text(
                    'Downloading...',
                    style:
                        TextStyle(
                      fontWeight:
                          FontWeight.bold,
                      fontSize: 16,
                    ),
                  ),
                ),
                Text(
                  '${percentage.toStringAsFixed(0)}%',
                  style:
                      const TextStyle(
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 14),

            LinearProgressIndicator(
              value: _progress,
              minHeight: 8,
              borderRadius:
                  BorderRadius.circular(
                10,
              ),
            ),

            const SizedBox(height: 14),

            Text(
              _progress >= 0.99
                  ? 'Saving file to your device...'
                  : 'Downloading ${_media?.title ?? ''}',
              maxLines: 2,
              overflow:
                  TextOverflow.ellipsis,
              style: TextStyle(
                color:
                    Colors.grey.shade600,
              ),
            ),

            const SizedBox(height: 16),

            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed:
                    _cancelDownload,
                icon: const Icon(
                  Icons.cancel_outlined,
                ),
                label: const Text(
                  'Cancel Download',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ============================================================
  // COMPLETE CARD
  // ============================================================

  Widget _buildCompleteCard() {
    return Card(
      child: Padding(
        padding:
            const EdgeInsets.all(18),
        child: Column(
          children: [
            const Icon(
              Icons.check_circle_rounded,
              size: 58,
              color: Colors.green,
            ),

            const SizedBox(height: 10),

            const Text(
              'Download Complete',
              style: TextStyle(
                fontSize: 19,
                fontWeight:
                    FontWeight.bold,
              ),
            ),

            const SizedBox(height: 6),

            Text(
              'Your media has been saved to your device.',
              textAlign:
                  TextAlign.center,
              style: TextStyle(
                color:
                    Colors.grey.shade600,
              ),
            ),

            if (_savedFileName != null) ...[
              const SizedBox(height: 10),

              Text(
                _savedFileName!,
                textAlign:
                    TextAlign.center,
                maxLines: 2,
                overflow:
                    TextOverflow.ellipsis,
                style:
                    const TextStyle(
                  fontWeight:
                      FontWeight.w500,
                ),
              ),
            ],

            const SizedBox(height: 16),

            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {
                  setState(() {
                    _downloadComplete =
                        false;
                  });
                },
                icon: const Icon(
                  Icons.download,
                ),
                label: const Text(
                  'Download Again',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}