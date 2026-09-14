import 'dart:io';

import 'package:flutter/material.dart';
import 'package:media_store_plus/media_store_plus.dart';

import 'home.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (Platform.isAndroid) {
    await MediaStore.ensureInitialized();

    MediaStore.appFolder = 'MP34 Downloader';
  }

  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'MP34 Downloader',
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: Colors.blue,
      ),
      home: const Homepage(
        username: 'User',
      ),
    );
  }
}