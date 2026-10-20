import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

class WindowSnapshot {
  const WindowSnapshot({
    this.x = 0,
    this.y = 0,
    this.width = 1080,
    this.height = 720,
    this.maximized = false,
  });

  final double x;
  final double y;
  final double width;
  final double height;
  final bool maximized;

  Map<String, dynamic> toJson() => {
        'x': x,
        'y': y,
        'width': width,
        'height': height,
        'maximized': maximized,
      };

  factory WindowSnapshot.fromJson(Map<String, dynamic> json) => WindowSnapshot(
        x: (json['x'] as num?)?.toDouble() ?? 0,
        y: (json['y'] as num?)?.toDouble() ?? 0,
        width: (json['width'] as num?)?.toDouble() ?? 1080,
        height: (json['height'] as num?)?.toDouble() ?? 720,
        maximized: json['maximized'] == true,
      );
}

class AppConfig {
  AppConfig({
    this.host = '',
    this.port = 14040,
    this.username = '',
    this.password = '',
    this.protocol = 'http',
    this.volume = 80,
    this.playMode = 'list',
    this.lastPlaylistId = '',
    this.lastSongId = '',
    this.lastPositionMs = 0,
    this.themeMode = 'system',
    this.reduceMotion = false,
    this.autostart = false,
    this.sidebarWidth = 200,
    this.window = const WindowSnapshot(),
    Map<String, String>? playlistCovers,
  }) : playlistCovers = playlistCovers ?? {};

  String host;
  int port;
  String username;
  String password;
  String protocol;
  int volume;
  String playMode;
  String lastPlaylistId;
  String lastSongId;
  int lastPositionMs;
  String themeMode;
  bool reduceMotion;
  bool autostart;
  double sidebarWidth;
  WindowSnapshot window;
  final Map<String, String> playlistCovers;

  bool get hasServer =>
      host.trim().isNotEmpty &&
      username.trim().isNotEmpty &&
      password.isNotEmpty;

  Map<String, dynamic> toJson() => {
        'host': host,
        'port': port,
        'username': username,
        'password': password,
        'protocol': protocol,
        'volume': volume,
        'playMode': playMode,
        'lastPlaylistId': lastPlaylistId,
        'lastSongId': lastSongId,
        'lastPositionMs': lastPositionMs,
        'themeMode': themeMode,
        'reduceMotion': reduceMotion,
        'autostart': autostart,
        'sidebarWidth': sidebarWidth,
        'window': window.toJson(),
        'playlistCovers': playlistCovers,
      };

  factory AppConfig.fromJson(Map<String, dynamic> json) => AppConfig(
        host: json['host']?.toString() ?? '',
        port: (json['port'] as num?)?.toInt() ?? 14040,
        username: json['username']?.toString() ?? '',
        password: json['password']?.toString() ?? '',
        protocol: json['protocol']?.toString() ?? 'http',
        volume: (json['volume'] as num?)?.toInt() ?? 80,
        playMode: json['playMode']?.toString() ?? 'list',
        lastPlaylistId: json['lastPlaylistId']?.toString() ?? '',
        lastSongId: json['lastSongId']?.toString() ?? '',
        lastPositionMs: (json['lastPositionMs'] as num?)?.toInt() ?? 0,
        themeMode: json['themeMode']?.toString() ?? 'system',
        reduceMotion: json['reduceMotion'] == true,
        autostart: json['autostart'] == true,
        sidebarWidth: (json['sidebarWidth'] as num?)?.toDouble() ?? 200,
        window: json['window'] is Map<String, dynamic>
            ? WindowSnapshot.fromJson(json['window'] as Map<String, dynamic>)
            : const WindowSnapshot(),
        playlistCovers: json['playlistCovers'] is Map
            ? (json['playlistCovers'] as Map).map(
                (key, value) => MapEntry(key.toString(), value.toString()),
              )
            : null,
      );
}

class ConfigStore {
  ConfigStore._();

  static final ConfigStore instance = ConfigStore._();

  File? _file;

  Directory get directory {
    final appData = Platform.environment['APPDATA'];
    final base =
        appData == null || appData.isEmpty ? Directory.current.path : appData;
    return Directory('$base/Yinjue-Mup');
  }

  File get file => _file ??= File('${directory.path}/config.json');

  Future<AppConfig> load() async {
    try {
      if (!await file.exists()) return AppConfig();
      final raw = await file.readAsString();
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) return AppConfig.fromJson(decoded);
    } catch (error, stack) {
      debugPrint('读取配置失败: $error\n$stack');
    }
    return AppConfig();
  }

  Future<void> save(AppConfig config) async {
    try {
      await directory.create(recursive: true);
      final temporary = File('${file.path}.tmp');
      await temporary.writeAsString(
        const JsonEncoder.withIndent('  ').convert(config.toJson()),
        flush: true,
      );
      if (await file.exists()) await file.delete();
      await temporary.rename(file.path);
    } catch (error, stack) {
      debugPrint('保存配置失败: $error\n$stack');
    }
  }
}
