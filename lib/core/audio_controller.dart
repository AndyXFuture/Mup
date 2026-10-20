import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';

import 'models.dart';
import 'subsonic_api.dart';

enum MupPlaybackState { stopped, playing, paused }

class MupAudioController extends ChangeNotifier {
  MupAudioController({int volume = 80, String mode = 'list'})
      : _volume = volume.clamp(0, 100),
        _lastAudibleVolume = volume > 0 ? volume.clamp(1, 100) : 80,
        _mode = mode {
    _player.setVolume(_volume / 100);
    _durationSub = _player.durationStream.listen((value) {
      if (value == null || value == duration) return;
      duration = value;
      notifyListeners();
    });
    _positionSub = _player.positionStream.listen((value) {
      if ((value - position).inMilliseconds.abs() < 120) return;
      position = value;
      notifyListeners();
    });
    _stateSub = _player.playerStateStream.listen((state) {
      if (state.processingState == ProcessingState.completed) {
        _onCompleted();
      }
      if (state.processingState == ProcessingState.loading ||
          state.processingState == ProcessingState.buffering) {
        buffering = true;
        notifyListeners();
      } else if (buffering) {
        buffering = false;
        notifyListeners();
      }
    });
  }

  final AudioPlayer _player = AudioPlayer();
  late final StreamSubscription<Duration?> _durationSub;
  late final StreamSubscription<Duration> _positionSub;
  late final StreamSubscription<PlayerState> _stateSub;
  Timer? _fadeTimer;
  Stopwatch? _fadeWatch;
  double _fadeStart = 0;
  double _fadeTarget = 0;
  bool _pauseAfterFade = false;
  int _volume;
  int _lastAudibleVolume;
  String _mode;
  String? _loadedSongId;
  final List<int> _history = [];

  SubsonicApi? api;
  List<Song> queue = [];
  int currentIndex = -1;
  Song? currentSong;
  Duration position = Duration.zero;
  Duration duration = Duration.zero;
  String? error;
  bool buffering = false;
  bool _intentPlaying = false;

  MupPlaybackState get state =>
      _intentPlaying ? MupPlaybackState.playing : MupPlaybackState.paused;
  bool get isPlaying => _intentPlaying;
  int get volume => _volume;
  String get mode => _mode;

  void attachApi(SubsonicApi value) => api = value;

  void restoreQueue(
    List<Song> songs, {
    String? preferredSongId,
    int positionMs = 0,
  }) {
    queue = List<Song>.of(songs);
    if (queue.isEmpty) {
      currentIndex = -1;
      currentSong = null;
    } else {
      final index = queue.indexWhere((song) => song.id == preferredSongId);
      currentIndex = index >= 0 ? index : 0;
      currentSong = queue[currentIndex];
      position = Duration(milliseconds: max(0, positionMs));
      duration = Duration(seconds: currentSong!.duration);
    }
    _intentPlaying = false;
    notifyListeners();
  }

  void replaceQueueKeepingCurrent(List<Song> songs) {
    if (songs.isEmpty) return;
    final currentId = currentSong?.id;
    queue = List<Song>.of(songs);
    currentIndex = currentId == null
        ? (currentIndex.clamp(0, queue.length - 1))
        : queue.indexWhere((song) => song.id == currentId);
    if (currentIndex < 0) currentIndex = 0;
    currentSong ??= queue[currentIndex];
    notifyListeners();
  }

  Future<void> setQueue(List<Song> songs, {int startIndex = 0}) async {
    if (songs.isEmpty) return;
    queue = List<Song>.of(songs);
    _history.clear();
    await playIndex(startIndex.clamp(0, queue.length - 1));
  }

  Future<void> playIndex(int index, {int positionMs = 0}) async {
    if (queue.isEmpty || index < 0 || index >= queue.length || api == null) {
      return;
    }
    _cancelFade();
    currentIndex = index;
    currentSong = queue[index];
    position = Duration(milliseconds: positionMs);
    duration = Duration(seconds: currentSong!.duration);
    error = null;
    buffering = true;
    if (_history.isEmpty || _history.last != index) _history.add(index);
    if (_history.length > 500) _history.removeAt(0);
    _intentPlaying = true;
    notifyListeners();
    try {
      _loadedSongId = currentSong!.id;
      await _player.setUrl(api!.streamUrl(currentSong!.id));
      if (_loadedSongId != currentSong?.id) return;
      if (positionMs > 0) {
        await _player.seek(Duration(milliseconds: positionMs));
      }
      if (!_intentPlaying) {
        buffering = false;
        await _player.setVolume(_volume / 100);
        notifyListeners();
        return;
      }
      await _player.setVolume(0);
      _player.play();
      await _fadeTo(_volume / 100, milliseconds: 3000);
    } catch (exception) {
      buffering = false;
      _intentPlaying = false;
      error = '无法播放：$exception';
      notifyListeners();
    }
  }

  Future<void> toggle() async {
    if (_intentPlaying) {
      await pause();
    } else {
      await play();
    }
  }

  Future<void> play() async {
    if (currentSong == null) {
      if (queue.isNotEmpty) await playIndex(max(0, currentIndex));
      return;
    }
    error = null;
    _intentPlaying = true;
    notifyListeners();
    try {
      if (_loadedSongId != currentSong!.id) {
        await playIndex(currentIndex, positionMs: position.inMilliseconds);
        return;
      }
      _player.play();
      await _fadeTo(_volume / 100, milliseconds: 3000);
    } catch (exception) {
      _intentPlaying = false;
      error = '无法播放：$exception';
      notifyListeners();
    }
  }

  Future<void> pause() async {
    _intentPlaying = false;
    _pauseAfterFade = true;
    notifyListeners();
    if (_player.playing) {
      await _fadeTo(0, milliseconds: 2000);
      if (_pauseAfterFade && !_intentPlaying) {
        await _player.pause();
        _pauseAfterFade = false;
      }
    } else {
      _cancelFade();
      _pauseAfterFade = false;
      await _player.setVolume(_volume / 100);
    }
  }

  Future<void> next({bool manual = true}) async {
    if (queue.isEmpty) return;
    int? nextIndex;
    if (_mode == 'random') {
      final candidates = [
        for (var i = 0; i < queue.length; i++)
          if (i != currentIndex) i
      ];
      nextIndex = candidates.isEmpty
          ? currentIndex
          : candidates[Random().nextInt(candidates.length)];
    } else {
      nextIndex = currentIndex + 1;
      if (nextIndex >= queue.length) {
        if (_mode == 'order' && !manual) {
          await stop();
          return;
        }
        nextIndex = 0;
      }
    }
    await playIndex(nextIndex);
  }

  Future<void> previous() async {
    if (queue.isEmpty) return;
    if (position.inMilliseconds > 3000) {
      await seek(Duration.zero);
      return;
    }
    if (_history.isNotEmpty) _history.removeLast();
    final index = _history.isEmpty ? currentIndex : _history.removeLast();
    await playIndex(index);
  }

  Future<void> seek(Duration value) async {
    final target = Duration(
      milliseconds:
          value.inMilliseconds.clamp(0, max(0, duration.inMilliseconds)),
    );
    position = target;
    notifyListeners();
    try {
      await _player.seek(target);
    } catch (_) {}
  }

  Future<void> setVolume(int value) async {
    _volume = value.clamp(0, 100);
    if (_volume > 0) _lastAudibleVolume = _volume;
    if (!_pauseAfterFade) {
      _cancelFade();
      await _player.setVolume(_volume / 100);
    }
    notifyListeners();
  }

  Future<void> toggleMute() => setVolume(_volume == 0 ? _lastAudibleVolume : 0);

  void setMode(String value) {
    if (!const ['list', 'random', 'single', 'order'].contains(value)) return;
    _mode = value;
    notifyListeners();
  }

  Future<void> stop() async {
    _intentPlaying = false;
    _cancelFade();
    _pauseAfterFade = false;
    await _player.stop();
    await _player.setVolume(_volume / 100);
    notifyListeners();
  }

  Future<void> _fadeTo(double target, {required int milliseconds}) async {
    _fadeTimer?.cancel();
    _fadeWatch = Stopwatch()..start();
    _fadeStart = _player.volume;
    _fadeTarget = target.clamp(0, 1);
    final completer = Completer<void>();
    _fadeTimer =
        Timer.periodic(const Duration(milliseconds: 30), (timer) async {
      final elapsed = _fadeWatch?.elapsedMilliseconds ?? milliseconds;
      final t = min(1.0, elapsed / milliseconds);
      final value = _fadeStart + (_fadeTarget - _fadeStart) * t;
      await _player.setVolume(value.clamp(0, 1));
      if (t >= 1) {
        timer.cancel();
        if (!completer.isCompleted) completer.complete();
      }
    });
    await completer.future;
  }

  void _cancelFade() {
    _fadeTimer?.cancel();
    _fadeTimer = null;
    _fadeWatch?.stop();
    _fadeWatch = null;
  }

  Future<void> _onCompleted() async {
    if (_mode == 'single') {
      await seek(Duration.zero);
      await play();
      return;
    }
    await next(manual: false);
  }

  @override
  void dispose() {
    _cancelFade();
    unawaited(_durationSub.cancel());
    unawaited(_positionSub.cancel());
    unawaited(_stateSub.cancel());
    unawaited(_player.dispose());
    super.dispose();
  }
}
