import 'package:flutter/material.dart';
import 'package:media_downloader/models/analyser.dart';
import 'package:media_downloader/services/media_api.dart';

class Homepage extends StatefulWidget {
  const Homepage({super.key});

  @override
  State<Homepage> createState() => _HomepageState();
}

class _HomepageState extends State<Homepage> {
  final _linkController = TextEditingController();
  final _mediaApi = MediaApi();
  String? _statusMessage;
  MediaInfo? _media;
  bool _isLoading = false;

  bool _isValidUrl(String value) {
    final uri = Uri.tryParse(value);
    return uri != null && uri.hasScheme && uri.host.isNotEmpty;
  }

  Future<void> _startDownload() async {
    final link = _linkController.text.trim();
    if (!_isValidUrl(link)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid media link.')),
      );
      return;
    }

    setState(() {
      _isLoading = true;
      _media = null;
      _statusMessage = 'Checking your media link...';
    });

    try {
      final media = await _mediaApi.analyse(link);
      if (!mounted) return;

      setState(() {
        _media = media;
        _statusMessage = 'Media is ready to download.';
      });
    } on MediaApiException catch (error) {
      if (!mounted) return;
      setState(() => _statusMessage = error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() => _statusMessage = 'Unable to analyse this media link.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  void dispose() {
    _linkController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: SafeArea(
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                colorScheme.primary.withOpacity(0.34),
                const Color(0xFFF7F2FF),
                colorScheme.surface,
              ],
              stops: const [0, 0.45, 1],
            ),
          ),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 22, 20, 22),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _Header(colorScheme: colorScheme),
                    const SizedBox(height: 22),
                    _LinkInput(
                      controller: _linkController,
                      isLoading: _isLoading,
                      onDownload: _startDownload,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      "Reminder: Respect creators' work and intellectual property rights.",
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 20),
                    _SocialPrompt(colorScheme: colorScheme),
                    const SizedBox(height: 14),
                    const _SocialRow(),
                    if (_statusMessage != null || _isLoading || _media != null)
                      _DownloadStatus(
                        colorScheme: colorScheme,
                        isLoading: _isLoading,
                        media: _media,
                        message: _statusMessage,
                      ),
                    const SizedBox(height: 22),
                    _SectionTitle(colorScheme: colorScheme),
                    const SizedBox(height: 12),
                    _RecentDownloadCard(media: _media),
                    const SizedBox(height: 16),
                    _PremiumCard(colorScheme: colorScheme),
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _isLoading ? null : _startDownload,
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(56),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(28),
                        ),
                        backgroundColor: colorScheme.primary,
                        foregroundColor: colorScheme.onPrimary,
                        textStyle: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      child: Text(_isLoading ? 'Checking...' : 'Download'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.colorScheme});

  final ColorScheme colorScheme;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Row(
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: colorScheme.onPrimary.withOpacity(0.55),
              width: 2,
            ),
            image: const DecorationImage(
              image: AssetImage('lib/asset/1.png'),
              fit: BoxFit.cover,
              alignment: Alignment.topCenter,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Video Downloader',
                style: textTheme.titleLarge?.copyWith(
                  color: colorScheme.onSurface,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                'Download from any platform instantly',
                style: textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
        Container(
          width: 46,
          height: 46,
          decoration: BoxDecoration(
            color: colorScheme.surface,
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                color: colorScheme.shadow.withOpacity(0.08),
                blurRadius: 18,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Icon(
            Icons.workspace_premium_rounded,
            color: colorScheme.onSurface,
          ),
        ),
      ],
    );
  }
}

class _LinkInput extends StatelessWidget {
  const _LinkInput({
    required this.controller,
    required this.isLoading,
    required this.onDownload,
  });

  final TextEditingController controller;
  final bool isLoading;
  final VoidCallback onDownload;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Row(
      children: [
        Expanded(
          child: SizedBox(
            height: 52,
            child: TextField(
              controller: controller,
              keyboardType: TextInputType.url,
              textInputAction: TextInputAction.done,
              style: const TextStyle(fontSize: 13),
              decoration: InputDecoration(
                filled: true,
                fillColor: colorScheme.surface.withOpacity(0.88),
                hintText: 'Paste your link here or auto-detect',
                hintStyle: TextStyle(
                  color: colorScheme.onSurfaceVariant,
                  fontSize: 13,
                ),
                prefixIcon: Icon(
                  Icons.link_rounded,
                  color: colorScheme.onSurfaceVariant,
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(26),
                  borderSide: BorderSide(
                    color: colorScheme.outlineVariant.withOpacity(0.8),
                  ),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(26),
                  borderSide: BorderSide(color: colorScheme.primary, width: 1.4),
                ),
              ),
              onSubmitted: (_) => onDownload(),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Container(
          width: 52,
          height: 52,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                colorScheme.primary,
                colorScheme.secondary,
              ],
            ),
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                color: colorScheme.primary.withOpacity(0.28),
                blurRadius: 18,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: IconButton(
            onPressed: isLoading ? null : onDownload,
            icon: isLoading
                ? SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: colorScheme.onPrimary,
                    ),
                  )
                : const Icon(Icons.file_download_outlined),
            color: colorScheme.onPrimary,
            tooltip: 'Download',
          ),
        ),
      ],
    );
  }
}

class _SocialPrompt extends StatelessWidget {
  const _SocialPrompt({required this.colorScheme});

  final ColorScheme colorScheme;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Divider(color: colorScheme.outlineVariant)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Text(
            'Open Social App to Copy Link',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: colorScheme.onSurfaceVariant,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Expanded(child: Divider(color: colorScheme.outlineVariant)),
      ],
    );
  }
}

class _SocialRow extends StatelessWidget {
  const _SocialRow();

  static const _items = [
    _SocialItemData('TikTok', asset: 'lib/asset/tiktok.png'),
    _SocialItemData('Instagram', asset: 'lib/asset/instagram.png'),
    _SocialItemData('Facebook', asset: 'lib/asset/facebook.png'),
    _SocialItemData('X', text: 'X', background: Colors.black),
    _SocialItemData('Youtube',asset: 'lib/asset/youtube.png' ),
  ];

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: _items.map((item) => _SocialItem(item)).toList(),
    );
  }
}

class _SocialItem extends StatelessWidget {
  const _SocialItem(this.item);

  final _SocialItemData item;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return SizedBox(
      width: 62,
      child: Column(
        children: [
          Material(
            color: item.background ?? colorScheme.surface,
            shape: const CircleBorder(),
            elevation: 2,
            shadowColor: colorScheme.shadow.withOpacity(0.12),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: () {},
              child: SizedBox(
                width: 52,
                height: 52,
                child: item.asset != null
                    ? ClipOval(
                        child: Image.asset(item.asset!, fit: BoxFit.cover),
                      )
                    : Center(
                        child: Text(
                          item.text!,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 23,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            item.label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: colorScheme.onSurfaceVariant,
              fontSize: 11,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}

class _SocialItemData {
  const _SocialItemData(
    this.label, {
    this.asset,
    this.text,
    this.background,
  });

  final String label;
  final String? asset;
  final String? text;
  final Color? background;
}

class _DownloadStatus extends StatelessWidget {
  const _DownloadStatus({
    required this.colorScheme,
    required this.isLoading,
    required this.media,
    required this.message,
  });

  final ColorScheme colorScheme;
  final bool isLoading;
  final MediaInfo? media;
  final String? message;

  @override
  Widget build(BuildContext context) {
    final title = media?.title ?? message ?? '';
    final subtitle = media?.platform ?? 'Preparing your download';

    return Padding(
      padding: const EdgeInsets.only(top: 18),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: colorScheme.surface.withOpacity(0.82),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: colorScheme.primary.withOpacity(0.16),
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: colorScheme.primary.withOpacity(0.12),
                shape: BoxShape.circle,
              ),
              child: isLoading
                  ? Padding(
                      padding: const EdgeInsets.all(10),
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: colorScheme.primary,
                      ),
                    )
                  : Icon(Icons.check_rounded, color: colorScheme.primary),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: colorScheme.onSurfaceVariant,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.colorScheme});

  final ColorScheme colorScheme;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            'Recently Download',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w800,
              color: colorScheme.onSurface,
            ),
          ),
        ),
        TextButton(
          onPressed: () {},
          style: TextButton.styleFrom(
            foregroundColor: colorScheme.onSurfaceVariant,
            visualDensity: VisualDensity.compact,
          ),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('View all'),
              SizedBox(width: 4),
              Icon(Icons.chevron_right_rounded, size: 18),
            ],
          ),
        ),
      ],
    );
  }
}

class _RecentDownloadCard extends StatelessWidget {
  const _RecentDownloadCard({required this.media});

  final MediaInfo? media;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      decoration: BoxDecoration(
        color: colorScheme.surface.withOpacity(0.94),
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withOpacity(0.08),
            blurRadius: 22,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 12, 12),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundImage: const AssetImage('lib/asset/1.png'),
                  backgroundColor: colorScheme.primaryContainer,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        media?.title ?? 'Reya Ramani',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        media?.platform ?? '@reyaramani458',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: colorScheme.onSurfaceVariant,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: () {},
                  icon: const Icon(Icons.file_download_outlined),
                  tooltip: 'Download',
                  visualDensity: VisualDensity.compact,
                ),
                IconButton(
                  onPressed: () {},
                  icon: const Icon(Icons.share_outlined),
                  tooltip: 'Share',
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
          ),
          AspectRatio(
            aspectRatio: 1.75,
            child: Stack(
              fit: StackFit.expand,
              children: [
                _RecentPreview(media: media),
                DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.transparent,
                        Colors.black.withOpacity(0.18),
                      ],
                    ),
                  ),
                ),
                Center(
                  child: Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: colorScheme.surface.withOpacity(0.9),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.play_arrow_rounded,
                      color: colorScheme.primary,
                      size: 30,
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
}

class _RecentPreview extends StatelessWidget {
  const _RecentPreview({required this.media});

  final MediaInfo? media;

  @override
  Widget build(BuildContext context) {
    final thumbnail = media?.thumbnail.trim() ?? '';
    if (thumbnail.isNotEmpty) {
      return Image.network(
        thumbnail,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _LocalPreview(),
      );
    }

    return const _LocalPreview();
  }
}

class _LocalPreview extends StatelessWidget {
  const _LocalPreview();

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      'lib/asset/1.png',
      fit: BoxFit.cover,
      alignment: Alignment.center,
    );
  }
}

class _PremiumCard extends StatelessWidget {
  const _PremiumCard({required this.colorScheme});

  final ColorScheme colorScheme;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surface.withOpacity(0.94),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: colorScheme.outlineVariant.withOpacity(0.6),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: const Color(0xFFFF9F1C).withOpacity(0.14),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.workspace_premium_rounded,
              color: Color(0xFFFF9F1C),
              size: 23,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Premium Features',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 3),
                Text(
                  'Remove watermarks, download audio, and unlock exclusive features.',
                  style: TextStyle(
                    color: colorScheme.onSurfaceVariant,
                    fontSize: 12,
                    height: 1.35,
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

