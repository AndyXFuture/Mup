import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'models.dart';
import 'secret_protection.dart';

class WindowSnapshot {
  const WindowSnapshot({
    this.x = 0,
    this.y = 0,
    this.width = 1080,
    this.height = 720,
    this.maximized = false,
    this.hasPosition = false,
  });

  final double x;
  final double y;
  final double width;
  final double height;
  final bool maximized;
  final bool hasPosition;

  Map<String, dynamic> toJson() => {
        'x': x,
        'y': y,
        'width': width,
        'height': height,
        'maximized': maximized,
        'hasPosition': hasPosition,
      };

  factory WindowSnapshot.fromJson(Map<String, dynamic> json) => WindowSnapshot(
        x: (json['x'] as num?)?.toDouble() ?? 0,
        y: (json['y'] as num?)?.toDouble() ?? 0,
        width: (json['width'] as num?)?.toDouble() ?? 1080,
        height: (json['height'] as num?)?.toDouble() ?? 720,
        maximized: json['maximized'] == true,
        hasPosition: json['hasPosition'] == true ||
            ((json['x'] as num?)?.toDouble() ?? 0) != 0 ||
            ((json['y'] as num?)?.toDouble() ?? 0) != 0,
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
    List<Song>? recentSongs,
  })  : playlistCovers = playlistCovers ?? {},
        recentSongs = recentSongs ?? [];

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
  final List<Song> recentSongs;

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
        'recentSongs': recentSongs.map((song) => song.toJson()).toList(),
      };

  factory AppConfig.fromJson(Map<String, dynamic> json) {
    final passwordIsProtected = json['passwordProtected'] == true;
    var password = json['password']?.toString() ?? '';
    if (passwordIsProtected) {
      try {
        password = SecretProtection.unprotectSecret(password);
      } catch (error) {
        debugPrint('无法解密已保存的服务器密码: $error');
        password = '';
      }
    }
    return AppConfig(
      host: json['host']?.toString() ?? '',
      port: (json['port'] as num?)?.toInt() ?? 14040,
      username: json['username']?.toString() ?? '',
      password: password,
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
      recentSongs: json['recentSongs'] is List
          ? (json['recentSongs'] as List)
              .whereType<Map>()
              .map((node) => Song.fromJson(Map<String, dynamic>.from(node)))
              .toList()
          : null,
    );
  }
}

class ConfigStore {
  ConfigStore._();

  static final ConfigStore instance = ConfigStore._();

  File? _file;
  Future<bool> _writeTail = Future<bool>.value(true);
  String? loadWarning;

  Directory get directory {
    final appData = Platform.environment['APPDATA'];
    final base =
        appData == null || appData.isEmpty ? Directory.current.path : appData;
    return Directory('$base/Yinjue-Mup');
  }

  File get file => _file ??= File('${directory.path}/config.json');

  Future<AppConfig> load() async {
    loadWarning = null;
    for (final candidate in [
      file,
      File('${file.path}.bak'),
    ]) {
      try {
        if (!await candidate.exists()) continue;
        final raw = await candidate.readAsString();
        final decoded = jsonDecode(raw);
        if (decoded is Map<String, dynamic>) {
          final config = AppConfig.fromJson(decoded);
          if (decoded['passwordProtected'] == true && config.password.isEmpty) {
            loadWarning = '已保存的服务器密码无法解密，请重新输入密码。';
          }
          if (candidate.path == file.path) {
            if (decoded['passwordProtected'] != true &&
                config.password.isNotEmpty &&
                Platform.isWindows) {
              if (!await save(config)) {
                loadWarning = '无法将旧版明文密码迁移为安全存储，请检查配置目录权限。';
              }
            } else if (decoded['passwordProtected'] == true) {
              await _refreshBackup();
            }
          } else if (config.password.isNotEmpty) {
            if (!await save(config)) {
              loadWarning = '配置备份无法恢复到安全存储，请检查配置目录权限。';
            }
          }
          return config;
        }
      } catch (error, stack) {
        debugPrint('读取配置失败 (${candidate.path}): $error\n$stack');
      }
    }
    return AppConfig();
  }

  Future<bool> save(AppConfig config) {
    final snapshot = AppConfig.fromJson(config.toJson());
    final previous = _writeTail;
    final operation = previous.catchError((Object _) => false).then((_) async {
      final temporary = File(
        '${file.path}.tmp-${DateTime.now().microsecondsSinceEpoch}',
      );
      final backup = File('${file.path}.bak');
      try {
        await directory.create(recursive: true);
        final json = snapshot.toJson();
        final passwordIsProtected =
            Platform.isWindows && snapshot.password.isNotEmpty;
        if (passwordIsProtected) {
          json['password'] = SecretProtection.protectSecret(snapshot.password);
        }
        json['passwordProtected'] = passwordIsProtected;
        await temporary.writeAsString(
          const JsonEncoder.withIndent('  ').convert(json),
          flush: true,
        );
        if (await file.exists()) {
          if (await backup.exists()) await backup.delete();
          await file.rename(backup.path);
        }
        try {
          await temporary.rename(file.path);
          return await _refreshBackup();
        } catch (_) {
          if (!await file.exists() && await backup.exists()) {
            await backup.rename(file.path);
          }
          rethrow;
        }
      } catch (error, stack) {
        debugPrint('保存配置失败: $error\n$stack');
        return false;
      } finally {
        if (await temporary.exists()) {
          try {
            await temporary.delete();
          } catch (_) {}
        }
      }
    });
    _writeTail = operation;
    return operation;
  }

  Future<bool> _refreshBackup() async {
    final backup = File('${file.path}.bak');
    try {
      if (await backup.exists()) await backup.delete();
      await file.copy(backup.path);
      return true;
    } catch (error) {
      debugPrint('刷新配置备份失败: $error');
      return false;
    }
  }
}
