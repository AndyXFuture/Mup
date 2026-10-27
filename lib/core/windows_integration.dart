import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'audio_controller.dart';

class MediaKeyService {
  MediaKeyService(this.audio);

  final MupAudioController audio;
  static const MethodChannel _channel = MethodChannel('mup/windows/media');

  Future<void> register() async {
    if (!Platform.isWindows) return;
    _channel.setMethodCallHandler(_handleNativeCall);
    final started = await _channel.invokeMethod<bool>('start') ?? false;
    if (!started) debugPrint('Windows 媒体键钩子启动失败');
  }

  Future<void> unregister() async {
    if (!Platform.isWindows) return;
    try {
      await _channel.invokeMethod<void>('stop');
    } catch (_) {}
    _channel.setMethodCallHandler(null);
  }

  Future<void> markReady() async {
    if (!Platform.isWindows) return;
    try {
      await _channel.invokeMethod<void>('ready');
    } catch (_) {}
  }

  Future<void> _handleNativeCall(MethodCall call) async {
    if (call.method != 'media' || call.arguments is! Map) return;
    switch ((call.arguments as Map)['action']) {
      case 'play_pause':
        unawaited(audio.toggle());
      case 'next':
        unawaited(audio.next());
      case 'previous':
        unawaited(audio.previous());
    }
  }
}

class AutostartService {
  static const _valueName = 'Yinjue-Mup';
  static const _runKey = r'HKCU\Software\Microsoft\Windows\CurrentVersion\Run';

  Future<bool> isEnabled() async {
    if (!Platform.isWindows) return false;
    final result =
        await Process.run('reg', ['query', _runKey, '/v', _valueName]);
    return result.exitCode == 0;
  }

  Future<bool> setEnabled(bool enabled) async {
    if (!Platform.isWindows) return false;
    if (!enabled) {
      final result = await Process.run(
        'reg',
        ['delete', _runKey, '/v', _valueName, '/f'],
      );
      if (result.exitCode == 0) return true;
      final query = await Process.run(
        'reg',
        ['query', _runKey, '/v', _valueName],
      );
      return query.exitCode != 0;
    }
    final command = '"${Platform.resolvedExecutable}" --background';
    final result = await Process.run(
      'reg',
      ['add', _runKey, '/v', _valueName, '/t', 'REG_SZ', '/d', command, '/f'],
    );
    return result.exitCode == 0;
  }
}
