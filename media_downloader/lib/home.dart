import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../models/analyser.dart';
import '../services/media_api.dart';


class Homepage extends StatefulWidget {

  const Homepage({
    super.key,
  });

  @override
  State<Homepage> createState() =>
      _HomepageState();
}


class _HomepageState
    extends State<Homepage> {

  final TextEditingController
      _urlController =
      TextEditingController();

  final MediaApi _api =
      MediaApi.instance;

  MediaInfo? _media;

  CancelToken? _cancelToken;

  double _progress = 0;

  bool _isAnalyzing = false;

  bool _isDownloading = false;

  String? _error;

  String? _savedFile;


  // ======================================================
  // DISPOSE
  // ======================================================

  @override
  void dispose() {

    _urlController.dispose();

    super.dispose();
  }


  // ======================================================
  // ANALYZE
  // ======================================================

  Future<void> _analyze() async {

    final url =
        _urlController.text.trim();

    if (url.isEmpty) {

      _showError(
        'Please enter a media URL.',
      );

      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {

      _isAnalyzing = true;

      _error = null;

      _media = null;

      _savedFile = null;

      _progress = 0;
    });

    try {

      final media =
          await _api.analyze(url);

      if (!mounted) return;

      setState(() {

        _media = media;

        _error = null;
      });

    } catch (error) {

      if (!mounted) return;

      setState(() {

        _error =
            error.toString();
      });

    } finally {

      if (!mounted) return;

      setState(() {

        _isAnalyzing = false;
      });
    }
  }


  // ======================================================
  // START DOWNLOAD
  // ======================================================

  Future<void> _download() async {

    final media = _media;

    if (media == null) {

      _showError(
        'Analyze a media link first.',
      );

      return;
    }

    if (_isDownloading) {
      return;
    }

    setState(() {

      _isDownloading = true;

      _progress = 0;

      _error = null;

      _savedFile = null;
    });

    _cancelToken =
        CancelToken();

    try {

      final saved =
          await _api.download(
        media,
        cancelToken:
            _cancelToken,

        onProgress:
            (value) {

          if (!mounted) return;

          setState(() {

            _progress =
                value.clamp(0.0, 1.0);
          });
        },
      );

      if (!mounted) return;

      setState(() {

        _savedFile = saved;

        _progress = 1.0;
      });

    } on DownloadCancelledException {

      if (!mounted) return;

      setState(() {

        _error =
            'Download cancelled.';
      });

    } catch (error) {

      if (!mounted) return;

      setState(() {

        _error =
            error.toString();
      });

    } finally {

      _cancelToken = null;

      if (!mounted) return;

      setState(() {

        _isDownloading = false;
      });
    }
  }


  // ======================================================
  // CANCEL
  // ======================================================

  void _cancelDownload() {

    if (!_isDownloading) {
      return;
    }

    _cancelToken?.cancel(
      'cancel',
    );
  }


  // ======================================================
  // ERROR MESSAGE
  // ======================================================

  void _showError(
    String message,
  ) {

    ScaffoldMessenger.of(context)
        .showSnackBar(
      SnackBar(
        content: Text(message),
        behavior:
            SnackBarBehavior.floating,
      ),
    );
  }


  // ======================================================
  // BUILD
  // ======================================================

  @override
  Widget build(
    BuildContext context,
  ) {

    return Scaffold(

      backgroundColor:
          const Color(0xFFF5F7FA),

      appBar: AppBar(

        elevation: 0,

        backgroundColor:
            Colors.blue,

        foregroundColor:
            Colors.white,

        title: const Text(
          'MP34 Downloader',
          style: TextStyle(
            fontWeight:
                FontWeight.bold,
          ),
        ),

        centerTitle: true,
      ),

      body: SafeArea(

        child: SingleChildScrollView(

          padding:
              const EdgeInsets.all(20),

          child: Column(

            crossAxisAlignment:
                CrossAxisAlignment.start,

            children: [

              const SizedBox(
                height: 10,
              ),

              // ------------------------------------------------
              // HEADER
              // ------------------------------------------------

              const Text(
                'Download your media',
                style: TextStyle(
                  fontSize: 26,
                  fontWeight:
                      FontWeight.bold,
                ),
              ),

              const SizedBox(
                height: 8,
              ),

              Text(
                'Paste a video or media link below '
                'to analyze and download it.',
                style: TextStyle(
                  fontSize: 15,
                  color:
                      Colors.grey.shade700,
                ),
              ),

              const SizedBox(
                height: 24,
              ),

              // ------------------------------------------------
              // URL FIELD
              // ------------------------------------------------

              TextField(

                controller:
                    _urlController,

                keyboardType:
                    TextInputType.url,

                textInputAction:
                    TextInputAction.done,

                decoration:
                    InputDecoration(

                  hintText:
                      'Paste media URL',

                  prefixIcon:
                      const Icon(
                    Icons.link,
                  ),

                  filled: true,

                  fillColor:
                      Colors.white,

                  border:
                      OutlineInputBorder(
                    borderRadius:
                        BorderRadius.circular(
                      14,
                    ),
                    borderSide:
                        BorderSide.none,
                  ),

                  enabledBorder:
                      OutlineInputBorder(
                    borderRadius:
                        BorderRadius.circular(
                      14,
                    ),
                    borderSide:
                        BorderSide(
                      color:
                          Colors.grey.shade300,
                    ),
                  ),

                  focusedBorder:
                      OutlineInputBorder(
                    borderRadius:
                        BorderRadius.circular(
                      14,
                    ),
                    borderSide:
                        const BorderSide(
                      color: Colors.blue,
                      width: 2,
                    ),
                  ),
                ),
              ),

              const SizedBox(
                height: 14,
              ),

              // ------------------------------------------------
              // ANALYZE BUTTON
              // ------------------------------------------------

              SizedBox(
                width: double.infinity,
                height: 52,

                child:
                    ElevatedButton.icon(

                  onPressed:
                      _isAnalyzing ||
                              _isDownloading
                          ? null
                          : _analyze,

                  icon:
                      _isAnalyzing
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child:
                                  CircularProgressIndicator(
                                strokeWidth: 2,
                                color:
                                    Colors.white,
                              ),
                            )
                          : const Icon(
                              Icons.search,
                            ),

                  label:
                      Text(
                    _isAnalyzing
                        ? 'Analyzing...'
                        : 'Analyze Link',
                  ),

                  style:
                      ElevatedButton.styleFrom(
                    backgroundColor:
                        Colors.blue,
                    foregroundColor:
                        Colors.white,
                    shape:
                        RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(
                        14,
                      ),
                    ),
                  ),
                ),
              ),

              const SizedBox(
                height: 24,
              ),

              // ------------------------------------------------
              // ERROR
              // ------------------------------------------------

              if (_error != null)
                Container(

                  width:
                      double.infinity,

                  padding:
                      const EdgeInsets.all(15),

                  margin:
                      const EdgeInsets.only(
                    bottom: 20,
                  ),

                  decoration:
                      BoxDecoration(
                    color:
                        Colors.red.shade50,
                    borderRadius:
                        BorderRadius.circular(
                      14,
                    ),
                    border:
                        Border.all(
                      color:
                          Colors.red.shade200,
                    ),
                  ),

                  child: Row(

                    crossAxisAlignment:
                        CrossAxisAlignment.start,

                    children: [

                      Icon(
                        Icons.error_outline,
                        color:
                            Colors.red.shade700,
                      ),

                      const SizedBox(
                        width: 10,
                      ),

                      Expanded(
                        child: Text(
                          _error!,
                          style:
                              TextStyle(
                            color:
                                Colors.red.shade800,
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

              if (_isDownloading)
                _buildProgressCard(),

              // ------------------------------------------------
              // COMPLETED
              // ------------------------------------------------

              if (_savedFile != null)
                _buildCompleteCard(),
            ],
          ),
        ),
      ),
    );
  }


  // ======================================================
  // MEDIA CARD
  // ======================================================

  Widget _buildMediaCard() {

    final media = _media!;

    return Container(

      width: double.infinity,

      margin:
          const EdgeInsets.only(
        bottom: 20,
      ),

      decoration:
          BoxDecoration(
        color: Colors.white,
        borderRadius:
            BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            blurRadius: 12,
            offset:
                const Offset(0, 5),
            color:
                Colors.black.withOpacity(
              0.06,
            ),
          ),
        ],
      ),

      child: Column(

        crossAxisAlignment:
            CrossAxisAlignment.start,

        children: [

          // ------------------------------------------------
          // THUMBNAIL
          // ------------------------------------------------

          if (media.thumbnail.isNotEmpty)

            ClipRRect(
              borderRadius:
                  const BorderRadius.vertical(
                top: Radius.circular(18),
              ),

              child: Image.network(

                media.thumbnail,

                width: double.infinity,

                height: 200,

                fit: BoxFit.cover,

                errorBuilder:
                    (
                  context,
                  error,
                  stackTrace,
                ) {

                  return Container(
                    height: 200,
                    color:
                        Colors.grey.shade200,
                    child:
                        const Icon(
                      Icons.movie,
                      size: 60,
                      color:
                          Colors.grey,
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

                Text(
                  media.title,
                  maxLines: 3,
                  overflow:
                      TextOverflow.ellipsis,
                  style:
                      const TextStyle(
                    fontSize: 18,
                    fontWeight:
                        FontWeight.bold,
                  ),
                ),

                const SizedBox(
                  height: 8,
                ),

                Row(

                  children: [

                    const Icon(
                      Icons.public,
                      size: 18,
                      color:
                          Colors.blue,
                    ),

                    const SizedBox(
                      width: 6,
                    ),

                    Text(
                      media.platform,
                      style:
                          TextStyle(
                        color:
                            Colors.grey.shade700,
                        fontWeight:
                            FontWeight.w500,
                      ),
                    ),
                  ],
                ),

                const SizedBox(
                  height: 18,
                ),

                SizedBox(
                  width:
                      double.infinity,
                  height: 50,

                  child:
                      ElevatedButton.icon(

                    onPressed:
                        _isDownloading
                            ? null
                            : _download,

                    icon:
                        const Icon(
                      Icons.download,
                    ),

                    label:
                        const Text(
                      'Download',
                    ),

                    style:
                        ElevatedButton.styleFrom(
                      backgroundColor:
                          Colors.blue,
                      foregroundColor:
                          Colors.white,
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
        ],
      ),
    );
  }


  // ======================================================
  // PROGRESS CARD
  // ======================================================

  Widget _buildProgressCard() {

    final percentage =
        (_progress * 100)
            .toStringAsFixed(0);

    return Container(

      width: double.infinity,

      padding:
          const EdgeInsets.all(18),

      margin:
          const EdgeInsets.only(
        bottom: 20,
      ),

      decoration:
          BoxDecoration(
        color: Colors.white,
        borderRadius:
            BorderRadius.circular(18),
        border:
            Border.all(
          color:
              Colors.blue.shade100,
        ),
      ),

      child: Column(

        crossAxisAlignment:
            CrossAxisAlignment.start,

        children: [

          Row(

            children: [

              const Icon(
                Icons.downloading,
                color:
                    Colors.blue,
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
                '$percentage%',
                style:
                    const TextStyle(
                  fontWeight:
                      FontWeight.bold,
                ),
              ),
            ],
          ),

          const SizedBox(
            height: 15,
          ),

          LinearProgressIndicator(
            value:
                _progress,
            minHeight: 7,
            borderRadius:
                BorderRadius.circular(
              10,
            ),
          ),

          const SizedBox(
            height: 16,
          ),

          SizedBox(
            width: double.infinity,

            child:
                OutlinedButton.icon(

              onPressed:
                  _cancelDownload,

              icon:
                  const Icon(
                Icons.close,
              ),

              label:
                  const Text(
                'Cancel',
              ),

              style:
                  OutlinedButton.styleFrom(
                foregroundColor:
                    Colors.red,
                side:
                    BorderSide(
                  color:
                      Colors.red.shade300,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }


  // ======================================================
  // COMPLETE CARD
  // ======================================================

  Widget _buildCompleteCard() {

    return Container(

      width: double.infinity,

      padding:
          const EdgeInsets.all(18),

      decoration:
          BoxDecoration(
        color:
            Colors.green.shade50,
        borderRadius:
            BorderRadius.circular(18),
        border:
            Border.all(
          color:
              Colors.green.shade200,
        ),
      ),

      child: Row(

        children: [

          Container(

            padding:
                const EdgeInsets.all(10),

            decoration:
                BoxDecoration(
              color:
                  Colors.green.shade100,
              shape:
                  BoxShape.circle,
            ),

            child:
                const Icon(
              Icons.check,
              color:
                  Colors.green,
            ),
          ),

          const SizedBox(
            width: 12,
          ),

          Expanded(
            child: Column(

              crossAxisAlignment:
                  CrossAxisAlignment.start,

              children: [

                const Text(
                  'Download complete',
                  style:
                      TextStyle(
                    fontWeight:
                        FontWeight.bold,
                    fontSize: 16,
                  ),
                ),

                const SizedBox(
                  height: 4,
                ),

                Text(
                  'Saved to your device.',
                  style:
                      TextStyle(
                    color:
                        Colors.grey.shade700,
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