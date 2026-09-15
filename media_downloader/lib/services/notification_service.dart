import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static const String _channelId = 'mp34_downloads';
  static const String _channelName = 'Downloads';
  static const String _channelDescription =
      'Notifications for MP34 Downloader downloads.';

  static Future<void> initialize() async {
    const androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');

    const settings = InitializationSettings(
      android: androidSettings,
    );

    await _plugin.initialize(settings:settings);

    final android =
        _plugin.resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();

    await android?.requestNotificationsPermission();

    await android?.createNotificationChannel(
      const AndroidNotificationChannel(
        _channelId,
        _channelName,
        description: _channelDescription,
        importance: Importance.defaultImportance,
      ),
    );
  }

  static Future<void> showStarted({
    required String title,
    required String format,
  }) async {
    await _plugin.show(
      id: 1001,
      title: 'Download started',
      body: '$format • $title',
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDescription,
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
          ongoing: true,
          autoCancel: false,
          showProgress: true,
          maxProgress: 100,
          progress: 0,
        ),
      ),
    );
  }

  static Future<void> showProgress({
    required int progress,
    required String title,
  }) async {
    await _plugin.show(
      id: 1001,
      title: 'Downloading',
      body: '$progress% • $title',
      notificationDetails: NotificationDetails(
        android: const AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDescription,
          importance: Importance.low,
          priority: Priority.low,
          ongoing: true,
          autoCancel: false,
          showProgress: true,
          maxProgress: 100,
          indeterminate: false,
        ),
      ),
    );
  }

  static Future<void> showCompleted({
    required String title,
    required String format,
  }) async {
    await _plugin.show(
      id: 1001,
      title: 'Download complete',
      body: '$format saved successfully',
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDescription,
          importance: Importance.high,
          priority: Priority.high,
          ongoing: false,
          autoCancel: true,
        ),
      ),
    );
  }

  static Future<void> showError({
    required String message,
  }) async {
    await _plugin.show(
      id: 1002,
      title: 'Download failed',
      body: message,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDescription,
          importance: Importance.high,
          priority: Priority.high,
          ongoing: false,
          autoCancel: true,
        ),
      ),
    );
  }

  static Future<void> cancel() async {
    await _plugin.cancel(id: 1001);
  }
}