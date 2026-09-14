import 'package:flutter/material.dart';
import 'package:media_store_plus/media_store_plus.dart';

import '/home.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await MediaStore.ensureInitialized();

  MediaStore.appFolder =
      'MP34 Downloader';

  runApp(
    const MP34DownloaderApp(),
  );
}

class MP34DownloaderApp
    extends StatelessWidget {

  const MP34DownloaderApp({
    super.key,
  });

  @override
  Widget build(
    BuildContext context,
  ) {

    return MaterialApp(
      debugShowCheckedModeBanner:
          false,

      title:
          'MP34 Downloader',

      theme:
          ThemeData(
        useMaterial3: true,

        colorSchemeSeed:
            Colors.blue,

        scaffoldBackgroundColor:
            const Color(
          0xFFF7F9FC,
        ),
      ),

      home:
          const Homepage(),
    );
  }
}