import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

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

  final MediaApi _api = MediaApi();

  MediaAnalysis? _media;

  CancelToken? _cancelToken;

  bool _isAnalyzing = false;
  bool _isDownloading = false;

  double _progress = 0;

  String _selectedFormat = 'MP4';

  String _status = '';

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
      _showMessage(
        'Please enter a media URL.',
      );
      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {
      _isAnalyzing = true;
      _media = null;
      _status = 'Analyzing media...';
    });

    try {
      final result = await _api.analyze(url);

      if (!mounted) return;

      setState(() {
        _media = result;
        _status = 'Media ready';
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _status = '';
      });

      _showMessage(
        _cleanError(error),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isAnalyzing = false;
        });
      }
    }
  }

  // ============================================================
  // DOWNLOAD
  // ============================================================

  Future<void> _download() async {
    if (_media == null) {
      _showMessage(
        'Analyze a media link first.',
      );
      return;
    }

    if (_selectedFormat == 'MP3') {
      _showMessage(
        'MP3 conversion will be added in the next step.',
      );
      return;
    }

    final directory =
        await getApplicationDocumentsDirectory();

    final downloadDirectory = Directory(
      '${directory.path}/MP34 Downloader',
    );

    if (!await downloadDirectory.exists()) {
      await downloadDirectory.create(
        recursive: true,
      );
    }

    final videoPath =
        '${downloadDirectory.path}/video.part';

    final audioPath =
        '${downloadDirectory.path}/audio.part';

    _cancelToken = CancelToken();

    setState(() {
      _isDownloading = true;
      _progress = 0;
      _status = 'Downloading video...';
    });

    try {
      // --------------------------------------------------------
      // VIDEO
      // --------------------------------------------------------

      await _api.downloadVideo(
        media: _media!,
        savePath: videoPath,
        cancelToken: _cancelToken!,
        onProgress: (received, total) {
          if (!mounted) return;

          if (total > 0) {
            setState(() {
              _progress =
                  received / total * 0.75;
            });
          }
        },
      );

      if (_cancelToken!.isCancelled) {
        return;
      }

      setState(() {
        _status = 'Downloading audio...';
      });

      // --------------------------------------------------------
      // AUDIO
      // --------------------------------------------------------

      await _api.downloadAudio(
        media: _media!,
        savePath: audioPath,
        cancelToken: _cancelToken!,
        onProgress: (received, total) {
          if (!mounted) return;

          if (total > 0) {
            setState(() {
              _progress =
                  0.75 +
                  (received / total * 0.25);
            });
          }
        },
      );

      if (_cancelToken!.isCancelled) {
        return;
      }

      setState(() {
        _progress = 1;
        _status = 'Streams downloaded';
      });

      _showMessage(
        'Video and audio downloaded successfully.',
      );

    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) {
        _showMessage(
          'Download cancelled.',
        );
      } else {
        _showMessage(
          'Download failed: ${error.message}',
        );
      }
    } catch (error) {
      _showMessage(
        'Download failed: $error',
      );
    } finally {
      if (mounted) {
        setState(() {
          _isDownloading = false;
        });
      }
    }
  }

  // ============================================================
  // CANCEL DOWNLOAD
  // ============================================================

  void _cancelDownload() {
    if (_cancelToken != null &&
        !_cancelToken!.isCancelled) {
      _cancelToken!.cancel(
        'Download cancelled.',
      );
    }
  }

  // ============================================================
  // ERROR CLEANUP
  // ============================================================

  String _cleanError(Object error) {
    if (error is DioException) {
      if (error.response?.data is Map) {
        final data =
            Map<String, dynamic>.from(
          error.response!.data,
        );

        return data['detail']?.toString() ??
            'Request failed.';
      }

      return error.message ??
          'Something went wrong.';
    }

    return error
        .toString()
        .replaceFirst(
          'Exception: ',
          '',
        );
  }

  // ============================================================
  // MESSAGE
  // ============================================================

  void _showMessage(
    String message,
  ) {
    if (!mounted) return;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior:
              SnackBarBehavior.floating,
        ),
      );
  }

  // ============================================================
  // UI
  // ============================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor:
          const Color(0xFFF7F8FA),

      appBar: AppBar(
        elevation: 0,
        backgroundColor: Colors.white,
        foregroundColor:
            const Color(0xFF171717),

        title: const Row(
          children: [
            Icon(
              Icons.download_rounded,
              size: 25,
            ),
            SizedBox(width: 10),
            Text(
              'MP34 Downloader',
              style: TextStyle(
                fontWeight:
                    FontWeight.w700,
              ),
            ),
          ],
        ),
      ),

      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),

          child: Column(
            crossAxisAlignment:
                CrossAxisAlignment.start,

            children: [

              const SizedBox(height: 10),

              const Text(
                'Download media',
                style: TextStyle(
                  fontSize: 27,
                  fontWeight:
                      FontWeight.w700,
                  color:
                      Color(0xFF171717),
                ),
              ),

              const SizedBox(height: 6),

              Text(
                'Paste a video link and choose your format.',
                style: TextStyle(
                  fontSize: 15,
                  color:
                      Colors.grey.shade600,
                ),
              ),

              const SizedBox(height: 25),

              // ------------------------------------------------
              // URL FIELD
              // ------------------------------------------------

              Container(
                decoration:
                    BoxDecoration(
                  color: Colors.white,
                  borderRadius:
                      BorderRadius.circular(14),
                  border: Border.all(
                    color:
                        Colors.grey.shade300,
                  ),
                ),

                child: TextField(
                  controller:
                      _urlController,

                  keyboardType:
                      TextInputType.url,

                  decoration:
                      const InputDecoration(
                    hintText:
                        'Paste media URL here',

                    prefixIcon: Icon(
                      Icons.link_rounded,
                    ),

                    border:
                        InputBorder.none,

                    contentPadding:
                        EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 17,
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 14),

              // ------------------------------------------------
              // ANALYZE BUTTON
              // ------------------------------------------------

              SizedBox(
                width: double.infinity,
                height: 52,

                child: ElevatedButton(
                  onPressed:
                      _isAnalyzing ||
                              _isDownloading
                          ? null
                          : _analyze,

                  style:
                      ElevatedButton.styleFrom(
                    backgroundColor:
                        const Color(
                      0xFF1769E0,
                    ),

                    foregroundColor:
                        Colors.white,

                    elevation: 0,

                    shape:
                        RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(
                        12,
                      ),
                    ),
                  ),

                  child: _isAnalyzing
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child:
                              CircularProgressIndicator(
                            strokeWidth: 2,
                            color:
                                Colors.white,
                          ),
                        )
                      : const Text(
                          'Analyze',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight:
                                FontWeight.w600,
                          ),
                        ),
                ),
              ),

              const SizedBox(height: 25),

              // ------------------------------------------------
              // MEDIA CARD
              // ------------------------------------------------

              if (_media != null)
                _buildMediaCard(),

              // ------------------------------------------------
              // STATUS
              // ------------------------------------------------

              if (_status.isNotEmpty) ...[
                const SizedBox(height: 18),

                Text(
                  _status,
                  style: TextStyle(
                    color:
                        Colors.grey.shade700,
                    fontSize: 14,
                  ),
                ),
              ],

              const SizedBox(height: 15),

              // ------------------------------------------------
              // DOWNLOAD PROGRESS
              // ------------------------------------------------

              if (_isDownloading) ...[
                ClipRRect(
                  borderRadius:
                      BorderRadius.circular(
                    10,
                  ),

                  child:
                      LinearProgressIndicator(
                    value: _progress,
                    minHeight: 8,
                  ),
                ),

                const SizedBox(height: 10),

                Row(
                  mainAxisAlignment:
                      MainAxisAlignment
                          .spaceBetween,

                  children: [
                    Text(
                      '${(_progress * 100).toStringAsFixed(0)}%',
                      style:
                          const TextStyle(
                        fontWeight:
                            FontWeight.w600,
                      ),
                    ),

                    TextButton(
                      onPressed:
                          _cancelDownload,
                      child:
                          const Text(
                        'Cancel',
                      ),
                    ),
                  ],
                ),
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

  Widget _buildMediaCard() {
    final media = _media!;

    return Container(
      width: double.infinity,

      decoration: BoxDecoration(
        color: Colors.white,

        borderRadius:
            BorderRadius.circular(16),

        border: Border.all(
          color:
              Colors.grey.shade200,
        ),
      ),

      child: Padding(
        padding:
            const EdgeInsets.all(14),

        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,

          children: [

            // Thumbnail
            if (media.thumbnail.isNotEmpty)
              ClipRRect(
                borderRadius:
                    BorderRadius.circular(
                  12,
                ),

                child: Image.network(
                  media.thumbnail,

                  width: double.infinity,
                  height: 210,

                  fit: BoxFit.cover,

                  errorBuilder:
                      (
                    context,
                    error,
                    stackTrace,
                  ) {
                    return Container(
                      height: 210,
                      color:
                          Colors.grey.shade200,

                      child: const Center(
                        child: Icon(
                          Icons
                              .broken_image_outlined,
                          size: 40,
                        ),
                      ),
                    );
                  },
                ),
              ),

            const SizedBox(height: 15),

            // Platform
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets
                          .symmetric(
                    horizontal: 10,
                    vertical: 5,
                  ),

                  decoration:
                      BoxDecoration(
                    color:
                        const Color(
                      0xFFEFF4FF,
                    ),

                    borderRadius:
                        BorderRadius.circular(
                      20,
                    ),
                  ),

                  child: Text(
                    media.platform,
                    style:
                        const TextStyle(
                      color:
                          Color(0xFF1769E0),
                      fontSize: 12,
                      fontWeight:
                          FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 10),

            // Title
            Text(
              media.title,
              maxLines: 3,
              overflow:
                  TextOverflow.ellipsis,

              style: const TextStyle(
                fontSize: 17,
                fontWeight:
                    FontWeight.w600,
              ),
            ),

            const SizedBox(height: 20),

            const Text(
              'Format',
              style: TextStyle(
                fontWeight:
                    FontWeight.w600,
                fontSize: 14,
              ),
            ),

            const SizedBox(height: 10),

            // Format selection
            Row(
              children: [

                Expanded(
                  child:
                      _formatButton(
                    'MP4',
                    Icons
                        .video_file_outlined,
                  ),
                ),

                const SizedBox(width: 10),

                Expanded(
                  child:
                      _formatButton(
                    'MP3',
                    Icons
                        .audio_file_outlined,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 18),

            // Download
            SizedBox(
              width: double.infinity,
              height: 50,

              child:
                  ElevatedButton.icon(
                onPressed:
                    _isDownloading
                        ? null
                        : _download,

                icon: const Icon(
                  Icons
                      .download_rounded,
                ),

                label: Text(
                  _selectedFormat ==
                          'MP4'
                      ? 'Download MP4'
                      : 'Download MP3',
                ),

                style:
                    ElevatedButton.styleFrom(
                  backgroundColor:
                      const Color(
                    0xFF171717,
                  ),

                  foregroundColor:
                      Colors.white,

                  elevation: 0,

                  shape:
                      RoundedRectangleBorder(
                    borderRadius:
                        BorderRadius.circular(
                      12,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ============================================================
  // FORMAT BUTTON
  // ============================================================

  Widget _formatButton(
    String format,
    IconData icon,
  ) {
    final selected =
        _selectedFormat == format;

    return InkWell(
      onTap: _isDownloading
          ? null
          : () {
              setState(() {
                _selectedFormat =
                    format;
              });
            },

      borderRadius:
          BorderRadius.circular(12),

      child: Container(
        padding:
            const EdgeInsets.symmetric(
          vertical: 13,
        ),

        decoration: BoxDecoration(
          color: selected
              ? const Color(
                  0xFFEFF4FF,
                )
              : Colors.white,

          borderRadius:
              BorderRadius.circular(12),

          border: Border.all(
            color: selected
                ? const Color(
                    0xFF1769E0,
                  )
                : Colors.grey.shade300,
          ),
        ),

        child: Row(
          mainAxisAlignment:
              MainAxisAlignment.center,

          children: [
            Icon(
              icon,
              size: 20,
              color: selected
                  ? const Color(
                      0xFF1769E0,
                    )
                  : Colors.grey.shade700,
            ),

            const SizedBox(width: 7),

            Text(
              format,
              style: TextStyle(
                fontWeight:
                    FontWeight.w600,

                color: selected
                    ? const Color(
                        0xFF1769E0,
                      )
                    : Colors.grey.shade700,
              ),
            ),
          ],
        ),
      ),
    );
  }
}