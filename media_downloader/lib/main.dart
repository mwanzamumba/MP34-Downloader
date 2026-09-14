import 'package:flutter/material.dart';
import 'package:media_downloader/home.dart';

void main() {
  runApp(const MainApp());
}

class MainApp extends StatelessWidget {
  const MainApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: const ColorScheme.light(
          primary: Color.fromARGB(255, 139, 79, 232),
          secondary: Color.fromARGB(255, 172, 111, 237),
          surface: Color(0xFFFFFBFF),
          onPrimary: Colors.white,
          onSurface: Color(0xFF18151D),
          onSurfaceVariant: Color(0xFF6F6878),
        ),
        useMaterial3: true,
        fontFamily: 'Roboto',
      ),
      home: const Homepage(),
    );
  }
}
