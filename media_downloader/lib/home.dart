import 'package:flutter/material.dart';

import '../models/analyser.dart';
import '../services/media_api.dart';


class Homepage extends StatefulWidget {
  const Homepage({super.key});

  @override
  State<Homepage> createState() => _HomepageState();
}


class _HomepageState extends State<Homepage> {
  final TextEditingController _linkController =
      TextEditingController();

  final MediaApi _mediaApi = MediaApi();

  MediaInfo? _media;

  bool _isLoading = false;
  String _statusMessage = '';
  String? _errorMessage;

  MediaFormat? _selectedFormat;


  @override
  void dispose() {
    _linkController.dispose();
    super.dispose();
  }


  // ----------------------------------------------------------
  // ANALYZE LINK
  // ----------------------------------------------------------

  Future<void> _startAnalysis() async {
    final link = _linkController.text.trim();

    if (link.isEmpty) {
      setState(() {
        _errorMessage = 'Please enter a media link.';
        _statusMessage = '';
      });
      return;
    }

    FocusScope.of(context).unfocus();

    setState(() {
      _isLoading = true;
      _media = null;
      _selectedFormat = null;
      _errorMessage = null;
      _statusMessage = 'Checking your media link...';
    });

    try {
      final media = await _mediaApi.analyse(link);

      if (!mounted) return;

      setState(() {
        _media = media;
        _isLoading = false;
        _statusMessage = 'Media analyzed successfully.';
      });

      _selectRecommendedFormat(media);
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _media = null;
        _selectedFormat = null;
        _statusMessage = '';
        _errorMessage = _cleanError(e.toString());
      });
    }
  }


  // ----------------------------------------------------------
  // SELECT RECOMMENDED FORMAT
  // ----------------------------------------------------------

  void _selectRecommendedFormat(MediaInfo media) {
    MediaFormat? format;

    if (media.recommendedVideo != null) {
      format = media.recommendedVideo;
    } else if (media.progressiveFormats.isNotEmpty) {
      format = media.progressiveFormats.first;
    } else if (media.videoFormats.isNotEmpty) {
      format = media.videoFormats.first;
    } else if (media.audioFormats.isNotEmpty) {
      format = media.audioFormats.first;
    }

    if (mounted) {
      setState(() {
        _selectedFormat = format;
      });
    }
  }


  // ----------------------------------------------------------
  // DOWNLOAD
  // ----------------------------------------------------------

  Future<void> _downloadSelectedFormat(
    MediaFormat format,
  ) async {
    final media = _media;

    if (media == null) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
      _statusMessage = 'Preparing your download...';
    });

    try {
      final downloadUrl = await _mediaApi.download(
        url: _linkController.text.trim(),
        formatId: format.formatId,
        mediaType: format.hasAudio && format.hasVideo
            ? 'video'
            : format.hasAudio
                ? 'audio'
                : 'video',
      );

      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _statusMessage = 'Download is ready.';
      });

      _showDownloadDialog(downloadUrl);
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _isLoading = false;
        _statusMessage = '';
        _errorMessage = _cleanError(e.toString());
      });
    }
  }


  // ----------------------------------------------------------
  // DOWNLOAD DIALOG
  // ----------------------------------------------------------

  void _showDownloadDialog(String downloadUrl) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Download Ready'),
          content: const Text(
            'Your media has been prepared successfully.',
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context);
              },
              child: const Text('Close'),
            ),

            ElevatedButton(
              onPressed: () {
                Navigator.pop(context);

                // For now we show the generated URL.
                // Later we will connect this to a proper
                // file downloader/storage implementation.
                _showUrlDialog(downloadUrl);
              },
              child: const Text('Open Download'),
            ),
          ],
        );
      },
    );
  }


  // ----------------------------------------------------------
  // SHOW DOWNLOAD URL
  // ----------------------------------------------------------

  void _showUrlDialog(String url) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Download Link'),
          content: SelectableText(url),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(context);
              },
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }


  // ----------------------------------------------------------
  // ERROR CLEANING
  // ----------------------------------------------------------

  String _cleanError(String error) {
    return error
        .replaceFirst('Exception: ', '')
        .trim();
  }


  // ----------------------------------------------------------
  // FORMAT LIST
  // ----------------------------------------------------------

  List<MediaFormat> _availableFormats() {
    final media = _media;

    if (media == null) {
      return [];
    }

    final formats = <MediaFormat>[];

    // Progressive formats are already video + audio.
    formats.addAll(media.progressiveFormats);

    // Add video-only formats.
    for (final format in media.videoFormats) {
      if (!formats.any(
        (item) => item.formatId == format.formatId,
      )) {
        formats.add(format);
      }
    }

    // Add audio formats.
    for (final format in media.audioFormats) {
      if (!formats.any(
        (item) => item.formatId == format.formatId,
      )) {
        formats.add(format);
      }
    }

    return formats;
  }


  // ----------------------------------------------------------
  // FORMAT CARD
  // ----------------------------------------------------------

  Widget _buildFormatCard(MediaFormat format) {
    final bool selected =
        _selectedFormat?.formatId == format.formatId;

    return GestureDetector(
      onTap: _isLoading
          ? null
          : () {
              setState(() {
                _selectedFormat = format;
              });
            },
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected
                ? Colors.blue
                : Colors.grey.shade300,
            width: selected ? 2 : 1,
          ),
          color: selected
              ? Colors.blue.withValues(alpha: 0.06)
              : Colors.white,
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: Colors.blue.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                format.hasVideo
                    ? Icons.video_file_outlined
                    : Icons.audiotrack,
                color: Colors.blue,
              ),
            ),

            const SizedBox(width: 14),

            Expanded(
              child: Column(
                crossAxisAlignment:
                    CrossAxisAlignment.start,
                children: [
                  Text(
                    format.displayResolution,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 4),

                  Text(
                    '${format.ext.toUpperCase()} • '
                    '${format.displayType}',
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.grey.shade700,
                    ),
                  ),

                  const SizedBox(height: 4),

                  Text(
                    format.displaySize,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
            ),

            Radio<String>(
              value: format.formatId,
              groupValue: _selectedFormat?.formatId,
              onChanged: _isLoading
                  ? null
                  : (_) {
                      setState(() {
                        _selectedFormat = format;
                      });
                    },
            ),
          ],
        ),
      ),
    );
  }


  // ----------------------------------------------------------
  // MEDIA INFORMATION
  // ----------------------------------------------------------

  Widget _buildMediaInfo() {
    final media = _media;

    if (media == null) {
      return const SizedBox.shrink();
    }

    final formats = _availableFormats();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 24),

        // Thumbnail
        if (media.thumbnail != null)
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: Image.network(
              media.thumbnail!,
              width: double.infinity,
              height: 190,
              fit: BoxFit.cover,
              errorBuilder: (
                context,
                error,
                stackTrace,
              ) {
                return Container(
                  height: 190,
                  color: Colors.grey.shade200,
                  child: const Icon(
                    Icons.image_not_supported_outlined,
                    size: 50,
                  ),
                );
              },
            ),
          ),

        const SizedBox(height: 16),

        // Title
        Text(
          media.title,
          style: const TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
        ),

        const SizedBox(height: 8),

        Row(
          children: [
            const Icon(
              Icons.public,
              size: 17,
            ),

            const SizedBox(width: 6),

            Text(
              media.platform,
              style: TextStyle(
                color: Colors.grey.shade700,
              ),
            ),

            if (media.uploader != null) ...[
              const SizedBox(width: 12),
              const Icon(
                Icons.person_outline,
                size: 17,
              ),
              const SizedBox(width: 5),
              Expanded(
                child: Text(
                  media.uploader!,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: Colors.grey.shade700,
                  ),
                ),
              ),
            ],
          ],
        ),

        const SizedBox(height: 24),

        const Text(
          'Available Formats',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),

        const SizedBox(height: 10),

        if (formats.isEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.orange.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Text(
              'No downloadable formats were found.',
            ),
          )
        else
          ...formats.map(_buildFormatCard),

        const SizedBox(height: 8),

        if (_selectedFormat != null)
          SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton.icon(
              onPressed: _isLoading
                  ? null
                  : () {
                      _downloadSelectedFormat(
                        _selectedFormat!,
                      );
                    },
              icon: const Icon(
                Icons.download,
              ),
              label: Text(
                _isLoading
                    ? 'Preparing...'
                    : 'Download ${_selectedFormat!.displayResolution}',
              ),
            ),
          ),
      ],
    );
  }


  // ----------------------------------------------------------
  // BUILD
  // ----------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.grey.shade50,

      appBar: AppBar(
        title: const Text(
          'Video Downloader',
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
                CrossAxisAlignment.start,
            children: [

              // Header
              const Text(
                'Download from any platform instantly',
                style: TextStyle(
                  fontSize: 15,
                  color: Colors.grey,
                ),
              ),

              const SizedBox(height: 24),

              // URL field
              TextField(
                controller: _linkController,
                keyboardType:
                    TextInputType.url,
                textInputAction:
                    TextInputAction.done,
                decoration: InputDecoration(
                  hintText:
                      'Paste your video link',
                  prefixIcon: const Icon(
                    Icons.link,
                  ),
                  suffixIcon: IconButton(
                    icon: const Icon(
                      Icons.clear,
                    ),
                    onPressed: () {
                      _linkController.clear();

                      setState(() {
                        _media = null;
                        _selectedFormat = null;
                        _errorMessage = null;
                        _statusMessage = '';
                      });
                    },
                  ),
                  border: OutlineInputBorder(
                    borderRadius:
                        BorderRadius.circular(14),
                  ),
                  enabledBorder:
                      OutlineInputBorder(
                    borderRadius:
                        BorderRadius.circular(14),
                    borderSide: BorderSide(
                      color: Colors.grey.shade300,
                    ),
                  ),
                  focusedBorder:
                      OutlineInputBorder(
                    borderRadius:
                        BorderRadius.circular(14),
                    borderSide:
                        const BorderSide(
                      color: Colors.blue,
                      width: 2,
                    ),
                  ),
                  filled: true,
                  fillColor: Colors.white,
                ),
                onSubmitted: (_) {
                  _startAnalysis();
                },
              ),

              const SizedBox(height: 12),

              // Analyze button
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton.icon(
                  onPressed:
                      _isLoading
                          ? null
                          : _startAnalysis,
                  icon: _isLoading
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
                    _isLoading
                        ? 'Please wait...'
                        : 'Analyze Link',
                  ),
                ),
              ),

              // Status
              if (_statusMessage.isNotEmpty) ...[
                const SizedBox(height: 14),

                Row(
                  children: [
                    const Icon(
                      Icons.info_outline,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _statusMessage,
                        style: TextStyle(
                          color:
                              Colors.grey.shade700,
                        ),
                      ),
                    ),
                  ],
                ),
              ],

              // Error
              if (_errorMessage != null) ...[
                const SizedBox(height: 14),

                Container(
                  width: double.infinity,
                  padding:
                      const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.red
                        .withValues(alpha: 0.08),
                    borderRadius:
                        BorderRadius.circular(12),
                  ),
                  child: Row(
                    crossAxisAlignment:
                        CrossAxisAlignment.start,
                    children: [
                      const Icon(
                        Icons.error_outline,
                        color: Colors.red,
                      ),
                      const SizedBox(width: 10),
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

              // Media result
              _buildMediaInfo(),

              const SizedBox(height: 30),

              // Reminder
              Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.blue
                      .withValues(alpha: 0.06),
                  borderRadius:
                      BorderRadius.circular(14),
                ),
                child: const Row(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.info_outline,
                      color: Colors.blue,
                    ),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Please respect creators’ work, '
                        'copyright, and each platform’s '
                        'terms when downloading media.',
                        style: TextStyle(
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

