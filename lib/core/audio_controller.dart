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
      if (_disposed) return;
      if (value == null || value == duration) return;
      duration = value;
      _notify();
    });
    _positionSub = _player.positionStream.listen((value) {
      if (_disposed) return;
      if ((value - position).inMilliseconds.abs() < 120) return;
      position = value;
      positionListenable.value = position;
    });
    _stateSub = _player.playerStateStream.listen((state) {
      if (_disposed) return;
      if (state.processingState == ProcessingState.completed) {
        if (_intentPlaying &&
            _acceptCompletion &&
            _completionHandledForGeneration != _playbackGeneration) {
          final generation = _playbackGeneration;
          _completionHandledForGeneration = generation;
          unawaited(_onCompleted(generation));
        }
      } else if (state.processingState == ProcessingState.ready &&
          state.playing) {
        // Allows the same stream to complete again after single-track replay.
        _completionHandledForGeneration = -1;
      }
      if (state.processingState == ProcessingState.loading ||
          state.processingState == ProcessingState.buffering) {
        buffering = true;
        _notify();
      } else if (buffering) {
        buffering = false;
        _notify();
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
  Completer<bool>? _fadeCompleter;
  int _fadeGeneration = 0;
  int _volume;
  int _lastAudibleVolume;
  String _mode;
  String? _loadedSongId;
  final List<int> _history = [];
  int _playbackGeneration = 0;
  int _completionHandledForGeneration = -1;
  bool _acceptCompletion = true;
  bool _disposed = false;

  SubsonicApi? api;
  final ValueNotifier<Duration> positionListenable =
      ValueNotifier(Duration.zero);
  List<Song> queue = [];
  String? playbackQueueKey;
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
    String? queueKey,
  }) {
    _playbackGeneration++;
    _acceptCompletion = false;
    _cancelFade();
    _pauseAfterFade = false;
    _loadedSongId = null;
    playbackQueueKey = queueKey;
    queue = List<Song>.of(songs);
    if (queue.isEmpty) {
      currentIndex = -1;
      currentSong = null;
      position = Duration.zero;
      duration = Duration.zero;
    } else {
      final index = queue.indexWhere((song) => song.id == preferredSongId);
      currentIndex = index >= 0 ? index : 0;
      currentSong = queue[currentIndex];
      position = Duration(milliseconds: max(0, positionMs));
      duration = Duration(seconds: currentSong!.duration);
    }
    positionListenable.value = position;
    _intentPlaying = false;
    unawaited(_player.stop().catchError((Object _) {}));
    _notify();
  }

  bool replaceQueueKeepingCurrent(List<Song> songs, {String? queueKey}) {
    if (songs.isEmpty) return false;
    final currentId = currentSong?.id;
    if (currentId == null) return false;
    final nextIndex = songs.indexWhere((song) => song.id == currentId);
    if (nextIndex < 0) return false;
    queue = List<Song>.of(songs);
    currentIndex = nextIndex;
    currentSong = queue[currentIndex];
    playbackQueueKey = queueKey ?? playbackQueueKey;
    _notify();
    return true;
  }

  void updateSong(Song song) {
    var changed = false;
    final updatedQueue = <Song>[];
    for (final item in queue) {
      if (item.id == song.id) {
        updatedQueue.add(song);
        changed = true;
      } else {
        updatedQueue.add(item);
      }
    }
    queue = updatedQueue;
    if (currentSong?.id == song.id) {
      currentSong = song;
      changed = true;
    }
    if (changed) _notify();
  }

  Future<void> setQueue(
    List<Song> songs, {
    int startIndex = 0,
    String? queueKey,
  }) async {
    if (songs.isEmpty) return;
    queue = List<Song>.of(songs);
    playbackQueueKey = queueKey;
    _history.clear();
    await playIndex(startIndex.clamp(0, queue.length - 1));
  }

  Future<void> playIndex(int index, {int positionMs = 0}) async {
    if (queue.isEmpty || index < 0 || index >= queue.length || api == null) {
      return;
    }
    final generation = ++_playbackGeneration;
    _acceptCompletion = false;
    _cancelFade();
    _pauseAfterFade = false;
    currentIndex = index;
    currentSong = queue[index];
    position = Duration(milliseconds: positionMs);
    duration = Duration(seconds: currentSong!.duration);
    error = null;
    buffering = true;
    _loadedSongId = null;
    if (_history.isEmpty || _history.last != index) _history.add(index);
    if (_history.length > 500) _history.removeAt(0);
    _intentPlaying = true;
    _notify();
    try {
      await _player.setUrl(api!.streamUrl(currentSong!.id));
      if (!_isCurrent(generation)) return;
      _loadedSongId = currentSong!.id;
      if (positionMs > 0) {
        await _player.seek(Duration(milliseconds: positionMs));
        if (!_isCurrent(generation)) return;
      }
      if (!_intentPlaying) {
        buffering = false;
        await _player.setVolume(_volume / 100);
        if (generation == _playbackGeneration) _acceptCompletion = true;
        _notify();
        return;
      }
      await _player.setVolume(0);
      if (!_isCurrent(generation)) return;
      _startPlayer(generation);
      _acceptCompletion = true;
      await _fadeTo(_volume / 100, milliseconds: 3000);
    } catch (exception) {
      if (!_isCurrent(generation)) return;
      buffering = false;
      _intentPlaying = false;
      _loadedSongId = null;
      error = '无法播放：$exception';
      _acceptCompletion = false;
      _notify();
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
    _acceptCompletion = true;
    _cancelFade();
    _pauseAfterFade = false;
    error = null;
    _intentPlaying = true;
    _notify();
    try {
      if (_loadedSongId != currentSong!.id) {
        await playIndex(currentIndex, positionMs: position.inMilliseconds);
        return;
      }
      if (_player.processingState == ProcessingState.completed) {
        await _player.seek(Duration.zero);
        position = Duration.zero;
        positionListenable.value = position;
      }
      _startPlayer(_playbackGeneration);
      await _fadeTo(_volume / 100, milliseconds: 3000);
    } catch (exception) {
      _intentPlaying = false;
      error = '无法播放：$exception';
      _notify();
    }
  }

  Future<void> pause() async {
    _intentPlaying = false;
    _acceptCompletion = false;
    _pauseAfterFade = true;
    _notify();
    if (_player.playing) {
      final completed = await _fadeTo(0, milliseconds: 2000);
      if (completed && _pauseAfterFade && !_intentPlaying) {
        await _player.pause();
        _pauseAfterFade = false;
        await _player.setVolume(_volume / 100);
      }
    } else {
      _cancelFade();
      _pauseAfterFade = false;
      await _player.setVolume(_volume / 100);
    }
    _notify();
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
    positionListenable.value = target;
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
    _notify();
  }

  Future<void> toggleMute() => setVolume(_volume == 0 ? _lastAudibleVolume : 0);

  void setMode(String value) {
    if (!const ['list', 'random', 'single', 'order'].contains(value)) return;
    _mode = value;
    _notify();
  }

  Future<void> stop() async {
    _playbackGeneration++;
    _intentPlaying = false;
    _acceptCompletion = false;
    _cancelFade();
    _pauseAfterFade = false;
    _loadedSongId = null;
    await _player.stop();
    await _player.setVolume(_volume / 100);
    _notify();
  }

  void clearQueue() {
    _playbackGeneration++;
    _acceptCompletion = false;
    _cancelFade();
    _pauseAfterFade = false;
    _loadedSongId = null;
    playbackQueueKey = null;
    queue = [];
    currentIndex = -1;
    currentSong = null;
    position = Duration.zero;
    positionListenable.value = position;
    duration = Duration.zero;
    _intentPlaying = false;
    unawaited(_player.stop().catchError((Object _) {}));
    _notify();
  }

  Future<bool> _fadeTo(double target, {required int milliseconds}) async {
    _cancelFade();
    final generation = ++_fadeGeneration;
    _fadeWatch = Stopwatch()..start();
    _fadeStart = _player.volume;
    _fadeTarget = target.clamp(0, 1);
    final completer = Completer<bool>();
    _fadeCompleter = completer;
    _fadeTimer =
        Timer.periodic(const Duration(milliseconds: 30), (timer) async {
      if (generation != _fadeGeneration || _disposed) {
        timer.cancel();
        return;
      }
      final elapsed = _fadeWatch?.elapsedMilliseconds ?? milliseconds;
      final t = min(1.0, elapsed / milliseconds);
      final value = _fadeStart + (_fadeTarget - _fadeStart) * t;
      try {
        await _player.setVolume(value.clamp(0, 1));
      } catch (_) {
        timer.cancel();
        if (!completer.isCompleted) completer.complete(false);
        return;
      }
      if (t >= 1) {
        timer.cancel();
        if (!completer.isCompleted) completer.complete(true);
      }
    });
    final result = await completer.future;
    if (identical(_fadeCompleter, completer)) _fadeCompleter = null;
    return result;
  }

  void _cancelFade() {
    _fadeGeneration++;
    _fadeTimer?.cancel();
    _fadeTimer = null;
    _fadeWatch?.stop();
    _fadeWatch = null;
    final completer = _fadeCompleter;
    _fadeCompleter = null;
    if (completer != null && !completer.isCompleted) completer.complete(false);
  }

  Future<void> _onCompleted(int generation) async {
    if (!_isCurrent(generation) || !_intentPlaying) return;
    try {
      if (_mode == 'single') {
        await seek(Duration.zero);
        if (!_isCurrent(generation) || !_intentPlaying) return;
        await play();
      } else {
        await next(manual: false);
      }
    } catch (exception) {
      buffering = false;
      _intentPlaying = false;
      error = '无法切换到下一首：$exception';
      _notify();
    }
  }

  bool _isCurrent(int generation) =>
      !_disposed && generation == _playbackGeneration;

  void _startPlayer(int generation) {
    unawaited(_player.play().then<void>(
      (_) {},
      onError: (Object exception, StackTrace _) {
        if (!_isCurrent(generation) || !_intentPlaying) return;
        buffering = false;
        _intentPlaying = false;
        error = '无法播放：$exception';
        _notify();
      },
    ));
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _playbackGeneration++;
    _acceptCompletion = false;
    _cancelFade();
    unawaited(_durationSub.cancel());
    unawaited(_positionSub.cancel());
    unawaited(_stateSub.cancel());
    unawaited(_player.dispose());
    positionListenable.dispose();
    super.dispose();
  }
}
