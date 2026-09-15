import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import '../models/analyser.dart';
import '../services/media_api.dart';
import '../services/media_processor.dart';
import '../services/media_store_service.dart';
import '../services/notification_service.dart';

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

  String _status = '';

  String _selectedFormat = 'MP4';

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  // ============================================================
  // ANALYZE
  // ============================================================

  Future<void> _analyze() async {
    FocusScope.of(context).unfocus();

    final url = _urlController.text.trim();

    if (url.isEmpty) {
      _showMessage(
        'Please paste a media URL first.',
        isError: true,
      );
      return;
    }

    setState(() {
      _isAnalyzing = true;
      _media = null;
      _status = 'Analyzing media...';
      _progress = 0;
    });

    try {
      final result = await _api.analyze(url);

      if (!mounted) return;

      setState(() {
        _media = result;
        _status = 'Media ready to download.';
      });
    } on DioException catch (error) {
      if (!mounted) return;

      final message = _dioErrorMessage(error);

      setState(() {
        _status = message;
      });

      _showMessage(
        message,
        isError: true,
      );
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _status = 'Could not analyze this URL.';
      });

      _showMessage(
        'Could not analyze this media.',
        isError: true,
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
    final media = _media;

    if (media == null || _isDownloading) {
      return;
    }

    final directory =
        await getApplicationDocumentsDirectory();

    final safeName =
        _safeFileName(media.title);

    final videoPath =
        '${directory.path}/$safeName.video.part';

    final audioPath =
        '${directory.path}/$safeName.audio.part';

    final finalPath = _selectedFormat == 'MP4'
        ? '${directory.path}/$safeName.mp4'
        : '${directory.path}/$safeName.mp3';

    final cancelToken = CancelToken();

    _cancelToken = cancelToken;

    setState(() {
      _isDownloading = true;
      _progress = 0;
      _status = 'Preparing download...';
    });

    try {
      await NotificationService.showStarted(
        title: media.title,
        format: _selectedFormat,
      );

      // ----------------------------------------------------------
      // VIDEO
      // ----------------------------------------------------------

      setState(() {
        _status = 'Downloading video...';
      });

      await _api.downloadStream(
        url: media.video.url,
        savePath: videoPath,
        cancelToken: cancelToken,
        onProgress: (received, total) {
          if (!mounted || total <= 0) {
            return;
          }

          final value =
              (received / total) * 70;

          setState(() {
            _progress =
                value.clamp(0, 70);
          });

          NotificationService.showProgress(
            progress: _progress.round(),
            title: media.title,
          );
        },
      );

      // ----------------------------------------------------------
      // AUDIO
      // ----------------------------------------------------------

      setState(() {
        _status = 'Downloading audio...';
      });

      await _api.downloadStream(
        url: media.audio.url,
        savePath: audioPath,
        cancelToken: cancelToken,
        onProgress: (received, total) {
          if (!mounted || total <= 0) {
            return;
          }

          final value =
              70 + ((received / total) * 20);

          setState(() {
            _progress =
                value.clamp(70, 90);
          });

          NotificationService.showProgress(
            progress: _progress.round(),
            title: media.title,
          );
        },
      );

      // ----------------------------------------------------------
      // PROCESS
      // ----------------------------------------------------------

      if (_selectedFormat == 'MP4') {
        await _processMp4(
          media: media,
          videoPath: videoPath,
          audioPath: audioPath,
          finalPath: finalPath,
        );
      } else {
        await _processMp3(
          media: media,
          audioPath: audioPath,
          finalPath: finalPath,
        );
      }

      // ----------------------------------------------------------
      // SAVE TO ANDROID MEDIASTORE
      // ----------------------------------------------------------

      setState(() {
        _status =
            'Saving to your phone...';
        _progress = 97;
      });

      if (_selectedFormat == 'MP4') {
        await MediaStoreService.saveVideo(
          filePath: finalPath,
          fileName: '$safeName.mp4',
        );
      } else {
        await MediaStoreService.saveAudio(
          filePath: finalPath,
          fileName: '$safeName.mp3',
        );
      }

      // ----------------------------------------------------------
      // CLEAN TEMPORARY FILES
      // ----------------------------------------------------------

      await _deleteIfExists(videoPath);
      await _deleteIfExists(audioPath);
      await _deleteIfExists(finalPath);

      // ----------------------------------------------------------
      // COMPLETE
      // ----------------------------------------------------------

      await NotificationService.showCompleted(
        title: media.title,
        format: _selectedFormat,
      );

      if (!mounted) return;

      setState(() {
        _progress = 100;

        _status = _selectedFormat == 'MP4'
            ? 'MP4 saved to Movies / MP34 Downloader'
            : 'MP3 saved to Music / MP34 Downloader';
      });
    } on DioException catch (error) {
      if (CancelToken.isCancel(error)) {
        await NotificationService.cancel();

        await _cleanupFiles(
          videoPath,
          audioPath,
          finalPath,
        );

        if (!mounted) return;

        setState(() {
          _status = 'Download cancelled.';
          _progress = 0;
        });

        return;
      }

      await _cleanupFiles(
        videoPath,
        audioPath,
        finalPath,
      );

      await NotificationService.showError(
        message: 'Unable to download the media.',
      );

      if (!mounted) return;

      setState(() {
        _status =
            'Download failed: ${_dioErrorMessage(error)}';
      });
    } catch (error) {
      await _cleanupFiles(
        videoPath,
        audioPath,
        finalPath,
      );

      await NotificationService.showError(
        message: 'Download failed.',
      );

      if (!mounted) return;

      setState(() {
        _status =
            'Download failed.';
      });

      debugPrint(
        'MP34 Downloader error: $error',
      );
    } finally {
      _cancelToken = null;

      if (mounted) {
        setState(() {
          _isDownloading = false;
        });
      }
    }
  }

  // ============================================================
  // MP4 PROCESSING
  // ============================================================

  Future<void> _processMp4({
    required MediaAnalysis media,
    required String videoPath,
    required String audioPath,
    required String finalPath,
  }) async {
    if (!mounted) return;

    setState(() {
      _status =
          'Combining video and audio...';
      _progress = 92;
    });

    await NotificationService.showProgress(
      progress: 92,
      title: media.title,
    );

    await MediaProcessor.mergeToMp4(
      videoPath: videoPath,
      audioPath: audioPath,
      outputPath: finalPath,
    );
  }

  // ============================================================
  // MP3 PROCESSING
  // ============================================================

  Future<void> _processMp3({
    required MediaAnalysis media,
    required String audioPath,
    required String finalPath,
  }) async {
    if (!mounted) return;

    setState(() {
      _status =
          'Converting audio to MP3...';
      _progress = 92;
    });

    await NotificationService.showProgress(
      progress: 92,
      title: media.title,
    );

    await MediaProcessor.convertToMp3(
      audioPath: audioPath,
      outputPath: finalPath,
    );
  }

  // ============================================================
  // CANCEL
  // ============================================================

  void _cancelDownload() {
    if (!_isDownloading) {
      return;
    }

    _cancelToken?.cancel(
      'Cancelled by user.',
    );
  }

  // ============================================================
  // CLEAR
  // ============================================================

  void _clear() {
    if (_isAnalyzing || _isDownloading) {
      return;
    }

    FocusScope.of(context).unfocus();

    _urlController.clear();

    setState(() {
      _media = null;
      _progress = 0;
      _status = '';
      _selectedFormat = 'MP4';
    });
  }

  // ============================================================
  // FILE HELPERS
  // ============================================================

  Future<void> _deleteIfExists(
    String path,
  ) async {
    try {
      final file = File(path);

      if (await file.exists()) {
        await file.delete();
      }
    } catch (_) {}
  }

  Future<void> _cleanupFiles(
    String videoPath,
    String audioPath,
    String finalPath,
  ) async {
    await _deleteIfExists(videoPath);
    await _deleteIfExists(audioPath);
    await _deleteIfExists(finalPath);
  }

  String _safeFileName(String title) {
    var name = title.trim();

    if (name.isEmpty) {
      name = 'MP34 Download';
    }

    name = name.replaceAll(
      RegExp(r'[\\/:*?"<>|]'),
      '_',
    );

    name = name.replaceAll(
      RegExp(r'\s+'),
      ' ',
    );

    if (name.length > 80) {
      name = name
          .substring(0, 80)
          .trim();
    }

    return name;
  }

  // ============================================================
  // ERROR HANDLING
  // ============================================================

  String _dioErrorMessage(
    DioException error,
  ) {
    if (error.response != null) {
      final data = error.response?.data;

      if (data is Map &&
          data['detail'] != null) {
        return data['detail'].toString();
      }

      return 'Server returned '
          '${error.response?.statusCode}.';
    }

    if (error.type ==
        DioExceptionType.connectionTimeout) {
      return 'Connection timed out.';
    }

    if (error.type ==
        DioExceptionType.receiveTimeout) {
      return 'Download timed out.';
    }

    if (error.type ==
        DioExceptionType.cancel) {
      return 'Download cancelled.';
    }

    return error.message ??
        'Network error.';
  }

  // ============================================================
  // UI MESSAGE
  // ============================================================

  void _showMessage(
    String message, {
    bool isError = false,
  }) {
    if (!mounted) return;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          behavior:
              SnackBarBehavior.floating,
          backgroundColor:
              isError
                  ? Colors.red.shade700
                  : Colors.indigo,
          shape: RoundedRectangleBorder(
            borderRadius:
                BorderRadius.circular(12),
          ),
        ),
      );
  }

  // ============================================================
  // BUILD
  // ============================================================

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        elevation: 0,
        backgroundColor:
            Colors.transparent,
        surfaceTintColor:
            Colors.transparent,

        title: const Text(
          'MP34 Downloader',
          style: TextStyle(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.4,
          ),
        ),

        centerTitle: false,
      ),

      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(
            20,
            10,
            20,
            32,
          ),

          child: Column(
            crossAxisAlignment:
                CrossAxisAlignment.start,

            children: [
              _buildHeader(),

              const SizedBox(height: 24),

              _buildUrlSection(),

              const SizedBox(height: 20),

              if (_media != null)
                _buildMediaCard(),

              if (_media != null)
                const SizedBox(height: 18),

              if (_media != null)
                _buildFormatSelector(),

              if (_media != null)
                const SizedBox(height: 18),

              if (_media != null)
                _buildDownloadButton(),

              if (_isDownloading ||
                  _progress > 0)
                _buildProgressCard(),

              const SizedBox(height: 12),

              if (_status.isNotEmpty &&
                  !_isDownloading)
                _buildStatus(),

              const SizedBox(height: 20),

              _buildFooter(),
            ],
          ),
        ),
      ),
    );
  }

  // ============================================================
  // HEADER
  // ============================================================

  Widget _buildHeader() {
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,

      children: [
        Text(
          'Download your media',
          style: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w800,
            color: Colors.grey.shade900,
            letterSpacing: -0.8,
          ),
        ),

        const SizedBox(height: 7),

        Text(
          'Paste a supported media link and '
          'choose MP4 or MP3.',
          style: TextStyle(
            fontSize: 14,
            height: 1.5,
            color: Colors.grey.shade600,
          ),
        ),
      ],
    );
  }

  // ============================================================
  // URL SECTION
  // ============================================================

  Widget _buildUrlSection() {
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,

      children: [
        const Text(
          'Media URL',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
          ),
        ),

        const SizedBox(height: 9),

        TextField(
          controller: _urlController,

          enabled:
              !_isAnalyzing &&
              !_isDownloading,

          keyboardType:
              TextInputType.url,

          textInputAction:
              TextInputAction.done,

          onSubmitted: (_) {
            if (!_isAnalyzing &&
                !_isDownloading) {
              _analyze();
            }
          },

          decoration:
              InputDecoration(
            hintText:
                'https://example.com/video',

            prefixIcon:
                const Icon(
              Icons.link_rounded,
            ),

            suffixIcon:
                _urlController
                        .text
                        .isNotEmpty
                    ? IconButton(
                        onPressed:
                            _isDownloading
                                ? null
                                : () {
                                    _urlController
                                        .clear();
                                    setState(() {});
                                  },
                        icon:
                            const Icon(
                          Icons.close_rounded,
                        ),
                      )
                    : null,
          ),

          onChanged: (_) {
            setState(() {});
          },
        ),

        const SizedBox(height: 12),

        Row(
          children: [
            Expanded(
              child: SizedBox(
                height: 52,

                child:
                    ElevatedButton.icon(
                  onPressed:
                      _isAnalyzing ||
                              _isDownloading
                          ? null
                          : _analyze,

                  icon: _isAnalyzing
                      ? const SizedBox(
                          width: 19,
                          height: 19,
                          child:
                              CircularProgressIndicator(
                            strokeWidth: 2.5,
                            color:
                                Colors.white,
                          ),
                        )
                      : const Icon(
                          Icons
                              .search_rounded,
                        ),

                  label: Text(
                    _isAnalyzing
                        ? 'Analyzing...'
                        : 'Analyze',
                  ),

                  style:
                      ElevatedButton.styleFrom(
                    backgroundColor:
                        Colors.indigo,

                    foregroundColor:
                        Colors.white,

                    disabledBackgroundColor:
                        Colors.grey.shade300,

                    elevation: 0,

                    shape:
                        RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(
                        15,
                      ),
                    ),
                  ),
                ),
              ),
            ),

            const SizedBox(width: 10),

            SizedBox(
              height: 52,

              child:
                  OutlinedButton.icon(
                onPressed:
                    _isAnalyzing ||
                            _isDownloading
                        ? null
                        : _clear,

                icon: const Icon(
                  Icons
                      .clear_all_rounded,
                ),

                label:
                    const Text('Clear'),

                style:
                    OutlinedButton.styleFrom(
                  foregroundColor:
                      Colors.grey.shade800,

                  side: BorderSide(
                    color:
                        Colors.grey.shade300,
                  ),

                  shape:
                      RoundedRectangleBorder(
                    borderRadius:
                        BorderRadius.circular(
                      15,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  // ============================================================
  // MEDIA CARD
  // ============================================================

  Widget _buildMediaCard() {
    final media = _media!;

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,

        borderRadius:
            BorderRadius.circular(20),

        border: Border.all(
          color: Colors.grey.shade200,
        ),
      ),

      clipBehavior:
          Clip.antiAlias,

      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,

        children: [
          if (media.thumbnail.isNotEmpty)
            AspectRatio(
              aspectRatio: 16 / 9,

              child: Image.network(
                media.thumbnail,

                width: double.infinity,

                fit: BoxFit.cover,

                errorBuilder:
                    (_, __, ___) {
                  return Container(
                    color:
                        Colors.grey.shade100,

                    child: const Center(
                      child: Icon(
                        Icons
                            .image_not_supported_outlined,
                        size: 42,
                      ),
                    ),
                  );
                },

                loadingBuilder:
                    (
                  context,
                  child,
                  progress,
                ) {
                  if (progress == null) {
                    return child;
                  }

                  return Container(
                    color:
                        Colors.grey.shade100,

                    child:
                        const Center(
                      child:
                          CircularProgressIndicator(),
                    ),
                  );
                },
              ),
            ),

          Padding(
            padding:
                const EdgeInsets.all(18),

            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,

              children: [
                Container(
                  padding:
                      const EdgeInsets
                          .symmetric(
                    horizontal: 10,
                    vertical: 6,
                  ),

                  decoration:
                      BoxDecoration(
                    color:
                        Colors.indigo.shade50,

                    borderRadius:
                        BorderRadius.circular(
                      30,
                    ),
                  ),

                  child: Text(
                    media.platform,
                    style: TextStyle(
                      color:
                          Colors.indigo
                              .shade700,

                      fontSize: 12,

                      fontWeight:
                          FontWeight.w700,
                    ),
                  ),
                ),

                const SizedBox(
                  height: 12,
                ),

                Text(
                  media.title,

                  maxLines: 3,

                  overflow:
                      TextOverflow.ellipsis,

                  style: const TextStyle(
                    fontSize: 17,
                    height: 1.35,
                    fontWeight:
                        FontWeight.w700,
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
  // FORMAT SELECTOR
  // ============================================================

  Widget _buildFormatSelector() {
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,

      children: [
        const Text(
          'Download format',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
          ),
        ),

        const SizedBox(height: 10),

        Row(
          children: [
            Expanded(
              child: _formatCard(
                format: 'MP4',
                icon:
                    Icons
                        .video_file_rounded,
                subtitle:
                    'Video + audio',
              ),
            ),

            const SizedBox(width: 12),

            Expanded(
              child: _formatCard(
                format: 'MP3',
                icon:
                    Icons
                        .music_note_rounded,
                subtitle:
                    'Audio only',
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _formatCard({
    required String format,
    required IconData icon,
    required String subtitle,
  }) {
    final selected =
        _selectedFormat == format;

    return GestureDetector(
      onTap: _isDownloading
          ? null
          : () {
              setState(() {
                _selectedFormat =
                    format;
              });
            },

      child: AnimatedContainer(
        duration:
            const Duration(
          milliseconds: 180,
        ),

        padding:
            const EdgeInsets.all(15),

        decoration:
            BoxDecoration(
          color: selected
              ? Colors.indigo.shade50
              : Colors.white,

          borderRadius:
              BorderRadius.circular(18),

          border: Border.all(
            color: selected
                ? Colors.indigo
                : Colors.grey.shade300,

            width:
                selected ? 2 : 1,
          ),
        ),

        child: Row(
          children: [
            Container(
              width: 43,
              height: 43,

              decoration:
                  BoxDecoration(
                color: selected
                    ? Colors.indigo
                    : Colors.grey
                        .shade100,

                borderRadius:
                    BorderRadius.circular(
                  12,
                ),
              ),

              child: Icon(
                icon,

                color: selected
                    ? Colors.white
                    : Colors.grey.shade700,
              ),
            ),

            const SizedBox(width: 10),

            Expanded(
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.start,

                children: [
                  Text(
                    format,

                    style:
                        const TextStyle(
                      fontSize: 15,
                      fontWeight:
                          FontWeight.w800,
                    ),
                  ),

                  const SizedBox(
                    height: 3,
                  ),

                  Text(
                    subtitle,

                    style: TextStyle(
                      fontSize: 11,
                      color:
                          Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
            ),

            if (selected)
              const Icon(
                Icons
                    .check_circle_rounded,
                color:
                    Colors.indigo,
                size: 22,
              ),
          ],
        ),
      ),
    );
  }

  // ============================================================
  // DOWNLOAD BUTTON
  // ============================================================

  Widget _buildDownloadButton() {
    return SizedBox(
      width: double.infinity,
      height: 56,

      child: ElevatedButton.icon(
        onPressed:
            _isDownloading
                ? null
                : _download,

        icon: _isDownloading
            ? const SizedBox(
                width: 21,
                height: 21,
                child:
                    CircularProgressIndicator(
                  strokeWidth: 2.5,
                  color: Colors.white,
                ),
              )
            : const Icon(
                Icons
                    .download_rounded,
              ),

        label: Text(
          _isDownloading
              ? 'Downloading...'
              : 'Download $_selectedFormat',

          style: const TextStyle(
            fontSize: 16,
            fontWeight:
                FontWeight.w800,
          ),
        ),

        style:
            ElevatedButton.styleFrom(
          backgroundColor:
              Colors.indigo,

          foregroundColor:
              Colors.white,

          disabledBackgroundColor:
              Colors.grey.shade300,

          elevation: 0,

          shape:
              RoundedRectangleBorder(
            borderRadius:
                BorderRadius.circular(
              16,
            ),
          ),
        ),
      ),
    );
  }

  // ============================================================
  // PROGRESS CARD
  // ============================================================

  Widget _buildProgressCard() {
    return Container(
      margin:
          const EdgeInsets.only(top: 18),

      padding:
          const EdgeInsets.all(18),

      decoration:
          BoxDecoration(
        color: Colors.white,

        borderRadius:
            BorderRadius.circular(18),

        border: Border.all(
          color: Colors.grey.shade200,
        ),
      ),

      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,

        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,

                decoration:
                    BoxDecoration(
                  color:
                      Colors.indigo.shade50,

                  borderRadius:
                      BorderRadius.circular(
                    11,
                  ),
                ),

                child: const Icon(
                  Icons
                      .downloading_rounded,
                  color:
                      Colors.indigo,
                  size: 21,
                ),
              ),

              const SizedBox(width: 11),

              Expanded(
                child: Text(
                  _status.isEmpty
                      ? 'Preparing...'
                      : _status,

                  maxLines: 2,

                  overflow:
                      TextOverflow.ellipsis,

                  style:
                      const TextStyle(
                    fontWeight:
                        FontWeight.w700,
                  ),
                ),
              ),

              const SizedBox(width: 8),

              Text(
                '${_progress.round()}%',

                style:
                    const TextStyle(
                  fontWeight:
                      FontWeight.w800,
                ),
              ),
            ],
          ),

          const SizedBox(height: 15),

          ClipRRect(
            borderRadius:
                BorderRadius.circular(
              20,
            ),

            child:
                LinearProgressIndicator(
              value:
                  _progress / 100,

              minHeight: 8,
            ),
          ),

          const SizedBox(height: 14),

          SizedBox(
            width: double.infinity,

            child:
                OutlinedButton.icon(
              onPressed:
                  _cancelDownload,

              icon: const Icon(
                Icons
                    .stop_circle_outlined,
              ),

              label:
                  const Text(
                'Cancel download',
              ),

              style:
                  OutlinedButton.styleFrom(
                foregroundColor:
                    Colors.red.shade700,

                side: BorderSide(
                  color:
                      Colors.red.shade200,
                ),

                shape:
                    RoundedRectangleBorder(
                  borderRadius:
                      BorderRadius.circular(
                    13,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ============================================================
  // STATUS
  // ============================================================

  Widget _buildStatus() {
    final success =
        _progress >= 100;

    return Container(
      width: double.infinity,

      padding:
          const EdgeInsets.all(14),

      decoration:
          BoxDecoration(
        color: success
            ? Colors.green.shade50
            : Colors.grey.shade100,

        borderRadius:
            BorderRadius.circular(14),
      ),

      child: Row(
        children: [
          Icon(
            success
                ? Icons
                    .check_circle_rounded
                : Icons.info_outline_rounded,

            color: success
                ? Colors.green.shade700
                : Colors.grey.shade700,
          ),

          const SizedBox(width: 10),

          Expanded(
            child: Text(
              _status,

              style: TextStyle(
                color: success
                    ? Colors.green.shade800
                    : Colors.grey.shade800,

                fontWeight:
                    FontWeight.w600,

                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ============================================================
  // FOOTER
  // ============================================================

  Widget _buildFooter() {
    return Center(
      child: Text(
        'MP34 Downloader',
        style: TextStyle(
          color: Colors.grey.shade500,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}