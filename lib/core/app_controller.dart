import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

import 'app_config.dart';
import 'audio_controller.dart';
import 'models.dart';
import 'subsonic_api.dart';
import 'windows_integration.dart';

enum AppStage { checking, connect, ready }

enum AppPage { library, player, settings }

class AppController extends ChangeNotifier {
  AppController()
      : audio = MupAudioController(),
        autostart = AutostartService() {
    audio.addListener(_onAudioChanged);
    audio.positionListenable.addListener(_onPlaybackProgress);
  }

  final MupAudioController audio;
  final AutostartService autostart;
  final ValueNotifier<String?> actionError = ValueNotifier<String?>(null);
  late AppConfig config;
  AppConfig? _draftConfig;
  SubsonicApi? _api;
  AppStage stage = AppStage.checking;
  AppPage page = AppPage.library;
  List<Playlist> playlists = [];
  List<Song> songs = [];
  List<Album> albums = [];
  List<Artist> artists = [];
  List<LyricLine> lyrics = [];
  Playlist? activePlaylist;
  String activeNav = 'home';
  String contentTitle = '最近添加';
  String contentSubtitle = '';
  String headerCoverId = '';
  String searchQuery = '';
  String? connectError;
  String? contentError;
  String? securityNotice;
  bool loading = true;
  bool compact = false;
  bool _demoMode = false;
  List<Artist> _demoArtists = const [];
  bool _disposed = false;
  int _requestToken = 0;
  int _connectGeneration = 0;
  bool _canCancelConnect = false;
  AppPage _pageBeforeConnect = AppPage.library;
  String _detailArtist = '';
  Timer? _saveTimer;
  Timer? _positionSaveTimer;

  SubsonicApi? get api => _api;
  bool get canCancelConnect => _canCancelConnect;
  AppConfig get draftConfig => _draftConfig ??= AppConfig(
        host: config.host,
        port: config.port,
        username: config.username,
        password: config.password,
        protocol: config.protocol,
      );

  Future<void> initialize() async {
    config = await ConfigStore.instance.load();
    securityNotice = ConfigStore.instance.loadWarning;
    final actualAutostart = await autostart.isEnabled();
    config.autostart = actualAutostart;
    audio.setVolume(config.volume);
    audio.setMode(config.playMode);
    _draftConfig = AppConfig(
      host: config.host,
      port: config.port,
      username: config.username,
      password: config.password,
      protocol: config.protocol,
    );

    if (!config.hasServer) {
      stage = AppStage.connect;
      loading = false;
      connectError = securityNotice;
      _notify();
      return;
    }

    final client = SubsonicApi(config);
    _api = client;
    audio.attachApi(client);
    stage = AppStage.checking;
    loading = true;
    _notify();
    if (!await client.ping()) {
      stage = AppStage.connect;
      loading = false;
      connectError = '无法连接上次的服务器，请检查设置';
      _notify();
      return;
    }
    stage = AppStage.ready;
    await _loadStartupContent();
  }

  void prepareDemo({String themeMode = 'dark'}) {
    _demoMode = true;
    config = AppConfig(
      host: 'music.example.com',
      port: 14040,
      username: 'demo',
      password: '',
      themeMode: themeMode,
      volume: 68,
    );
    _draftConfig = AppConfig(
      host: config.host,
      port: config.port,
      username: config.username,
      protocol: config.protocol,
    );
    config.playlistCovers['demo-favorites'] =
        'asset:assets/demo/playlist-favorites.jpg';
    playlists = const [
      Playlist(id: 'demo-favorites', name: '我喜欢', songCount: 2),
    ];
    activePlaylist = playlists.first;
    activeNav = 'playlist:${activePlaylist!.id}';
    contentTitle = activePlaylist!.name;
    contentSubtitle = '2 首 · 8 分 23 秒';
    songs = const [
      Song(
        id: 'demo-1',
        title: '旅行家说',
        artist: '毛不易',
        artistId: 'demo-artist-mao',
        album: '幼鸟指南',
        albumId: 'demo-album-youngbird',
        duration: 309,
        coverId: 'asset:assets/demo/traveler.jpg',
      ),
      Song(
        id: 'demo-2',
        title: 'Floating Bits (PRIME TIME Edition)',
        artist: 'Embark Studios',
        artistId: 'demo-artist-embark',
        album: 'THE FINALS (PRIME TIME Original Soundtrack)',
        albumId: 'demo-album-finals',
        duration: 194,
        coverId: 'asset:assets/demo/floating-bits.jpg',
      ),
    ];
    _demoArtists = const [
      Artist(
        id: 'demo-artist-xue',
        name: '薛之谦',
        coverId: 'asset:assets/demo/artist-xue.jpg',
        songCount: 91,
        albumCount: 18,
      ),
      Artist(
        id: 'demo-artist-mao',
        name: '毛不易',
        coverId: 'asset:assets/demo/artist-mao.jpg',
        songCount: 73,
        albumCount: 8,
      ),
    ];
    artists = [];
    audio.setVolume(68);
    audio.setMode('list');
    audio.restoreQueue(
      songs,
      preferredSongId: songs.first.id,
      positionMs: 83000,
    );
    lyrics = const [
      LyricLine(0, '听说远方 最神秘的角落'),
      LyricLine(6000, '每晚都燃起篝火 相爱的人围坐'),
      LyricLine(12000, '岁月也分外温柔 流过时变成歌'),
      LyricLine(18000, '被他们 轻声唱着'),
      LyricLine(24000, '你要去吗 趁天边还有光'),
      LyricLine(30000, '就像你来时一样 不必在意方向'),
      LyricLine(36000, '记得带上你当初 那少年的模样'),
    ];
    loading = false;
    contentError = null;
    stage = AppStage.ready;
    _notify();
  }

  Future<void> _loadStartupContent() async {
    final client = _api;
    if (client == null) return;
    loading = true;
    contentError = null;
    _notify();
    try {
      playlists = await client.getPlaylists();
      String? selectedPlaylistKey;
      if (playlists.isNotEmpty) {
        final selected =
            playlists.where((item) => item.id == config.lastPlaylistId);
        final playlist = selected.isNotEmpty ? selected.first : playlists.first;
        selectedPlaylistKey = 'playlist:${playlist.id}';
        await openPlaylist(playlist, preserveLoading: true);
      } else {
        await _loadAlbums(
          preserveLoading: true,
          title: '最近添加',
          navigation: 'home',
        );
      }
      audio.restoreQueue(
        songs,
        preferredSongId: config.lastSongId,
        positionMs: config.lastPositionMs,
        queueKey: selectedPlaylistKey,
      );
    } catch (error) {
      contentError = '加载曲库失败：$error';
    } finally {
      loading = false;
      _notify();
    }
  }

  Future<bool> connect(
    String host,
    int port,
    String username,
    String password,
    String protocol,
  ) async {
    final connectGeneration = ++_connectGeneration;
    final endpoint = _normalizeEndpoint(host, port, protocol);
    final candidate = AppConfig(
      host: endpoint.host,
      port: endpoint.port,
      username: username.trim(),
      password: password,
      protocol: endpoint.protocol,
      volume: config.volume,
      playMode: config.playMode,
      themeMode: config.themeMode,
      reduceMotion: config.reduceMotion,
      autostart: config.autostart,
      window: config.window,
    );
    if (candidate.port < 1 || candidate.port > 65535) {
      connectError = '端口必须是 1 到 65535 之间的数字';
      _notify();
      return false;
    }
    if (!candidate.hasServer) {
      connectError = '服务器地址、用户名和密码不能为空';
      _notify();
      return false;
    }
    loading = true;
    connectError = null;
    _notify();
    final client = SubsonicApi(candidate);
    final reachable = await client.ping();
    if (connectGeneration != _connectGeneration) {
      client.close();
      return false;
    }
    if (!reachable) {
      client.close();
      loading = false;
      connectError = '连接失败，请确认地址、端口和账号信息';
      _notify();
      return false;
    }
    // The server has accepted the connection. Commit it as one operation so a
    // late cancellation cannot leave the controller half-connected.
    _canCancelConnect = false;
    _api?.close();
    audio.clearQueue();
    config.host = candidate.host;
    config.port = candidate.port;
    config.username = candidate.username;
    config.password = candidate.password;
    config.protocol = candidate.protocol;
    _api = client;
    audio.attachApi(client);
    final saved = await ConfigStore.instance.save(config);
    securityNotice = saved ? null : '服务器密码无法安全保存，请检查配置目录权限。';
    await _loadStartupContent();
    stage = AppStage.ready;
    _notify();
    return true;
  }

  ({String host, int port, String protocol}) _normalizeEndpoint(
    String input,
    int fallbackPort,
    String fallbackProtocol,
  ) {
    var value = input.trim();
    var resolvedPort = fallbackPort;
    var resolvedProtocol = fallbackProtocol;
    if (value.startsWith('http://') || value.startsWith('https://')) {
      final uri = Uri.tryParse(value);
      if (uri != null) {
        value = uri.host;
        if (uri.port > 0) resolvedPort = uri.port;
        if (uri.scheme == 'http' || uri.scheme == 'https') {
          resolvedProtocol = uri.scheme;
        }
      }
    }
    return (
      host: value.replaceAll(RegExp(r'/$'), ''),
      port: resolvedPort,
      protocol: resolvedProtocol,
    );
  }

  Future<void> refreshCurrent() async {
    if (activePlaylist != null) {
      await openPlaylist(activePlaylist!, force: true);
      return;
    }
    if (activeNav.startsWith('album:')) {
      await _loadAlbumDetail(
        activeNav.substring('album:'.length),
        title: contentTitle,
        artist: _detailArtist,
        coverId: headerCoverId,
      );
      return;
    }
    if (activeNav.startsWith('artist:')) {
      await _loadArtistDetail(
        activeNav.substring('artist:'.length),
        title: contentTitle,
        coverId: headerCoverId,
      );
      return;
    }
    if (activeNav == 'search') {
      await search(searchQuery);
      return;
    }
    switch (activeNav) {
      case 'starred':
        await _loadSongs(
          contentTitle: '收藏',
          loadingLabel: '正在读取收藏',
          loader: () => _api!.getStarred(),
        );
      case 'recent':
        await _loadRecent();
      case 'artists':
        await _loadArtists();
      case 'albums':
        await _loadAlbums();
      default:
        await _loadAlbums(title: '最近添加', navigation: 'home');
    }
  }

  Future<void> refreshPlaylists() async {
    final client = _api;
    if (client == null) return;
    try {
      final result = await client.getPlaylists();
      final knownCounts = {
        for (final playlist in playlists)
          if (playlist.songCount > 0) playlist.id: playlist.songCount,
      };
      playlists = [
        for (final playlist in result)
          playlist.songCount > 0
              ? playlist
              : playlist.withSongCount(knownCounts[playlist.id] ?? 0),
      ];
      final activeId = activePlaylist?.id;
      if (activeId != null) {
        final refreshed = playlists.where((item) => item.id == activeId);
        if (refreshed.isNotEmpty) activePlaylist = refreshed.first;
      }
      _notify();
    } catch (error) {
      contentError = '刷新歌单列表失败：$error';
      _notify();
    }
  }

  Future<void> openPlaylist(Playlist playlist,
      {bool force = false, bool preserveLoading = false}) async {
    final client = _api;
    if (client == null) return;
    final token = ++_requestToken;
    activePlaylist = playlist;
    activeNav = 'playlist:${playlist.id}';
    contentTitle = playlist.name;
    contentSubtitle = '${playlist.songCount} 首';
    headerCoverId = playlist.coverId;
    _detailArtist = '';
    contentError = null;
    albums = [];
    artists = [];
    if (!preserveLoading) {
      loading = true;
      contentError = null;
      _notify();
    }
    try {
      final page = await client.getPlaylistSongs(playlist.id, complete: force);
      final result = page.songs;
      final totalCount = page.totalCount;
      _updatePlaylistSongCount(playlist.id, totalCount);
      final queueKey = 'playlist:${playlist.id}';
      if (force && audio.playbackQueueKey == queueKey) {
        audio.replaceQueueKeepingCurrent(result, queueKey: queueKey);
      }
      if (token != _requestToken) return;
      songs = result;
      contentSubtitle = totalCount > result.length
          ? '${result.length}/$totalCount 首 · 正在补全'
          : '${result.length} 首${_durationLabel(result)}';
      config.lastPlaylistId = playlist.id;
      _persistSoon();
      if (!force && totalCount > result.length) {
        unawaited(_hydrateFullPlaylist(playlist, token));
      }
    } catch (error) {
      if (token == _requestToken) contentError = '加载歌单失败：$error';
    } finally {
      if (!preserveLoading) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> _hydrateFullPlaylist(Playlist playlist, int token) async {
    final client = _api;
    if (client == null) return;
    try {
      final page = await client.getPlaylistSongs(playlist.id);
      final full = page.songs;
      _updatePlaylistSongCount(playlist.id, page.totalCount);
      final queueKey = 'playlist:${playlist.id}';
      if (audio.playbackQueueKey == queueKey) {
        audio.replaceQueueKeepingCurrent(full, queueKey: queueKey);
      }
      if (token != _requestToken || full.length <= songs.length) return;
      songs = full;
      contentSubtitle = '${full.length} 首${_durationLabel(full)}';
      _notify();
    } catch (_) {}
  }

  void _updatePlaylistSongCount(String playlistId, int count) {
    if (count <= 0) return;
    var changed = false;
    final updatedPlaylists = <Playlist>[];
    for (final item in playlists) {
      if (item.id == playlistId && item.songCount != count) {
        updatedPlaylists.add(item.withSongCount(count));
        changed = true;
      } else {
        updatedPlaylists.add(item);
      }
    }
    playlists = updatedPlaylists;
    final active = activePlaylist;
    if (active != null &&
        active.id == playlistId &&
        active.songCount != count) {
      activePlaylist = active.withSongCount(count);
      changed = true;
    }
    if (changed) _notify();
  }

  String _durationLabel(List<Song> items) {
    final seconds = items.fold<int>(0, (sum, song) => sum + song.duration);
    if (seconds <= 0) return '';
    final hours = seconds ~/ 3600;
    final minutes = (seconds % 3600) ~/ 60;
    return hours > 0 ? ' · $hours 小时 $minutes 分' : ' · $minutes 分';
  }

  Future<void> selectNavigation(String nav) async {
    if (_api == null) {
      activeNav = nav;
      activePlaylist = null;
      if (nav == 'artists') {
        artists = _demoArtists;
        contentTitle = '歌手';
        contentSubtitle = '${artists.length} 位歌手 · 按歌曲数量排序';
        albums = [];
        songs = [];
      }
      _notify();
      return;
    }
    activeNav = nav;
    activePlaylist = null;
    searchQuery = '';
    switch (nav) {
      case 'starred':
        await _loadSongs(
          contentTitle: '收藏',
          loadingLabel: '正在读取收藏',
          loader: () => _api!.getStarred(),
        );
      case 'recent':
        await _loadRecent();
      case 'artists':
        await _loadArtists();
      case 'albums':
        await _loadAlbums();
      default:
        await _loadAlbums(title: '最近添加', navigation: 'home');
    }
  }

  Future<void> _loadSongs({
    required String contentTitle,
    required String loadingLabel,
    required Future<List<Song>> Function() loader,
  }) async {
    final token = ++_requestToken;
    this.contentTitle = contentTitle;
    contentSubtitle = loadingLabel;
    songs = [];
    albums = [];
    artists = [];
    headerCoverId = '';
    loading = true;
    contentError = null;
    _notify();
    try {
      final result = await loader();
      if (token != _requestToken) return;
      songs = result;
      contentSubtitle = '${result.length} 首';
    } catch (error) {
      if (token == _requestToken) contentError = '加载失败：$error';
    } finally {
      if (token == _requestToken) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> _loadRecent() {
    return _loadSongs(
      contentTitle: '最近播放',
      loadingLabel: '正在读取本地播放记录',
      loader: () async => List<Song>.of(config.recentSongs),
    );
  }

  Future<void> _loadAlbums({
    bool preserveLoading = false,
    String title = '专辑',
    String navigation = 'albums',
  }) async {
    final client = _api;
    if (client == null) return;
    final token = ++_requestToken;
    activePlaylist = null;
    activeNav = navigation;
    contentTitle = title;
    contentSubtitle = '按最近添加排序';
    albums = [];
    songs = [];
    artists = [];
    headerCoverId = '';
    contentError = null;
    if (!preserveLoading) {
      loading = true;
      _notify();
    }
    try {
      final result = await client.getAlbums();
      if (token != _requestToken) return;
      albums = result;
      contentSubtitle = '${result.length} 张专辑';
    } catch (error) {
      if (token == _requestToken) contentError = '加载专辑失败：$error';
    } finally {
      if (!preserveLoading && token == _requestToken) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> _loadArtists() async {
    final client = _api;
    if (client == null) return;
    final token = ++_requestToken;
    activePlaylist = null;
    activeNav = 'artists';
    contentTitle = '歌手';
    contentSubtitle = '正在整理歌手列表';
    albums = [];
    songs = [];
    artists = [];
    headerCoverId = '';
    loading = true;
    contentError = null;
    _notify();
    try {
      final result = await client.getArtists();
      if (token != _requestToken) return;
      final counts = await client.getArtistSongCounts(result);
      if (token != _requestToken) return;
      artists = result
          .map((artist) => artist.withSongCount(counts[artist.id] ?? 0))
          .toList()
        ..sort((a, b) => b.songCount.compareTo(a.songCount));
      contentSubtitle = '${result.length} 位歌手 · 按歌曲数量排序';
    } catch (error) {
      if (token == _requestToken) contentError = '加载歌手失败：$error';
    } finally {
      if (token == _requestToken) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> openAlbum(Song song) async {
    if (song.albumId.isEmpty) return;
    await _loadAlbumDetail(
      song.albumId,
      title: song.album,
      artist: song.artist,
      coverId: song.coverId,
    );
  }

  Future<void> openArtist(Song song) async {
    if (song.artistId.isEmpty) return;
    await _loadArtistDetail(
      song.artistId,
      title: song.artist,
      coverId: '',
    );
  }

  Future<void> openArtistEntry(Artist artist) async {
    await _loadArtistDetail(
      artist.id,
      title: artist.name,
      coverId: artist.coverId,
    );
  }

  Future<void> openAlbumEntry(Album album) async {
    await _loadAlbumDetail(
      album.id,
      title: album.name,
      artist: album.artist,
      coverId: album.coverId,
    );
  }

  Future<void> _loadAlbumDetail(
    String albumId, {
    required String title,
    required String artist,
    required String coverId,
  }) async {
    final client = _api;
    if (client == null || albumId.isEmpty) return;
    page = AppPage.library;
    final token = ++_requestToken;
    activePlaylist = null;
    activeNav = 'album:$albumId';
    contentTitle = title;
    contentSubtitle = artist.isEmpty ? '正在读取专辑' : artist;
    headerCoverId = coverId;
    _detailArtist = artist;
    loading = true;
    songs = [];
    albums = [];
    artists = [];
    contentError = null;
    _notify();
    try {
      final result = await client.getAlbum(albumId);
      if (token != _requestToken) return;
      songs = result;
      contentSubtitle = artist.isEmpty
          ? '${result.length} 首'
          : '$artist · ${result.length} 首';
    } catch (error) {
      if (token == _requestToken) contentError = '加载专辑失败：$error';
    } finally {
      if (token == _requestToken) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> _loadArtistDetail(
    String artistId, {
    required String title,
    required String coverId,
  }) async {
    final client = _api;
    if (client == null || artistId.isEmpty) return;
    page = AppPage.library;
    final token = ++_requestToken;
    activePlaylist = null;
    activeNav = 'artist:$artistId';
    contentTitle = title;
    contentSubtitle = '正在读取歌手作品';
    headerCoverId = coverId;
    _detailArtist = '';
    loading = true;
    songs = [];
    albums = [];
    artists = [];
    contentError = null;
    _notify();
    try {
      final result = await client.getArtistSongs(artistId);
      if (token != _requestToken) return;
      songs = result;
      contentSubtitle = '${result.length} 首';
    } catch (error) {
      if (token == _requestToken) contentError = '加载歌手失败：$error';
    } finally {
      if (token == _requestToken) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> search(String query) async {
    final keyword = query.trim();
    if (keyword.isEmpty) {
      await selectNavigation('home');
      return;
    }
    final token = ++_requestToken;
    searchQuery = keyword;
    activePlaylist = null;
    activeNav = 'search';
    contentTitle = '搜索 “$keyword”';
    contentSubtitle = '正在搜索';
    contentError = null;
    headerCoverId = '';
    loading = true;
    songs = [];
    albums = [];
    artists = [];
    _notify();
    try {
      final result = await _api!.search(keyword);
      if (token != _requestToken) return;
      songs = result.$1;
      albums = result.$2;
      artists = result.$3;
      contentSubtitle =
          '${result.$1.length} 首歌曲 · ${result.$2.length} 张专辑 · ${result.$3.length} 位歌手';
    } catch (error) {
      if (token == _requestToken) contentError = '搜索失败：$error';
    } finally {
      if (token == _requestToken) {
        loading = false;
        _notify();
      }
    }
  }

  Future<void> playSong(Song song) async {
    final index = songs.indexWhere((item) => item.id == song.id);
    if (index < 0) return;
    if (audio.currentSong?.id == song.id) {
      await audio.toggle();
    } else {
      await audio.setQueue(songs, startIndex: index, queueKey: activeNav);
    }
  }

  Future<void> playAll({bool shuffle = false}) async {
    if (songs.isEmpty) return;
    audio.setMode(shuffle ? 'random' : 'list');
    final start = shuffle ? Random().nextInt(songs.length) : 0;
    await audio.setQueue(songs, startIndex: start, queueKey: activeNav);
  }

  bool get currentSongIsStarred => audio.currentSong?.starred == true;

  Future<void> toggleCurrentStar() async {
    final client = _api;
    final song = audio.currentSong;
    if (client == null || song == null) return;
    final value = !song.starred;
    try {
      await client.setStarred(song.id, value);
      final updated = song.withStarred(value);
      audio.updateSong(updated);
      final updatedSongs = [
        for (final item in songs) item.id == song.id ? updated : item,
      ];
      songs = value || activeNav != 'starred'
          ? updatedSongs
          : updatedSongs.where((item) => item.id != song.id).toList();
      for (var index = 0; index < config.recentSongs.length; index++) {
        if (config.recentSongs[index].id == song.id) {
          config.recentSongs[index] = updated;
        }
      }
      albums = List<Album>.of(albums);
      artists = List<Artist>.of(artists);
      _persistSoon();
      _notify();
    } catch (error) {
      contentError = '更新收藏失败：$error';
      actionError.value = null;
      actionError.value = '更新收藏失败，请检查连接后重试';
      _notify();
    }
  }

  void clearActionError() {
    actionError.value = null;
  }

  void openPlayer() {
    page = AppPage.player;
    _notify();
  }

  void dismissSecurityNotice() {
    securityNotice = null;
    _notify();
  }

  void openSettings() {
    page = AppPage.settings;
    _notify();
  }

  void openConnect() {
    _pageBeforeConnect = page;
    _canCancelConnect = config.hasServer && _api != null;
    _draftConfig = AppConfig(
      host: config.host,
      port: config.port,
      username: config.username,
      password: config.password,
      protocol: config.protocol,
    );
    connectError = null;
    stage = AppStage.connect;
    _notify();
  }

  void cancelConnect() {
    if (!_canCancelConnect) return;
    _connectGeneration++;
    connectError = null;
    loading = false;
    stage = AppStage.ready;
    page = _pageBeforeConnect;
    _canCancelConnect = false;
    _notify();
  }

  void openLibrary() {
    page = AppPage.library;
    _notify();
  }

  void setThemeMode(String mode) {
    config.themeMode = mode;
    _persistSoon();
    _notify();
  }

  void setReduceMotion(bool value) {
    config.reduceMotion = value;
    _persistSoon();
    _notify();
  }

  void setSidebarWidth(double value) {
    config.sidebarWidth = value.clamp(180, 300);
    _persistSoon();
    _notify();
  }

  Future<void> choosePlaylistCover() async {
    final playlist = activePlaylist;
    if (playlist == null) return;
    const group = XTypeGroup(
      label: '图片',
      extensions: ['jpg', 'jpeg', 'png', 'webp'],
    );
    final file = await openFile(acceptedTypeGroups: const [group]);
    if (file == null) return;
    await FileImage(File(file.path)).evict();
    config.playlistCovers[playlist.id] = file.path;
    _persistSoon();
    _notify();
  }

  Future<void> useServerPlaylistCover() async {
    final playlist = activePlaylist;
    if (playlist == null) return;
    config.playlistCovers.remove(playlist.id);
    final remote = coverUrlFor(playlist.coverId, size: 512);
    if (remote.isNotEmpty) {
      await NetworkImage(remote).evict();
    }
    _persistSoon();
    _notify();
  }

  Future<bool> setAutostart(bool value) async {
    final result = await autostart.setEnabled(value);
    if (result) {
      config.autostart = value;
      _persistSoon();
      _notify();
    }
    return result;
  }

  void setCompact(bool value) {
    if (compact == value) return;
    compact = value;
    _notify();
  }

  void _onAudioChanged() {
    final song = audio.currentSong;
    if (song != null && song.id != _lastSeenSongId) {
      _lastSeenSongId = song.id;
      _rememberSong(song);
      lyrics = [];
      _lastLyricIndex = -2;
      _loadLyrics(song);
    }
    if (song != null) {
      config.lastSongId = song.id;
    }
    config.volume = audio.volume;
    config.playMode = audio.mode;
    _notify();
  }

  void _rememberSong(Song song) {
    config.recentSongs.removeWhere((item) => item.id == song.id);
    config.recentSongs.insert(0, song);
    if (config.recentSongs.length > 100) {
      config.recentSongs.removeRange(100, config.recentSongs.length);
    }
    _persistSoon();
  }

  String? _lastSeenSongId;
  int _lastLyricIndex = -2;

  void _onPlaybackProgress() {
    if (_disposed) return;
    final index = activeLyricIndex;
    if (index != _lastLyricIndex) {
      _lastLyricIndex = index;
      _notify();
    }
    _positionSaveTimer ??= Timer(const Duration(seconds: 2), () {
      _positionSaveTimer = null;
      final song = audio.currentSong;
      if (song == null) return;
      config.lastSongId = song.id;
      config.lastPositionMs = audio.position.inMilliseconds;
      _persistSoon();
    });
  }

  Future<void> _loadLyrics(Song song) async {
    final client = _api;
    if (client == null) return;
    try {
      final result = await client.getLyrics(song);
      if (song.id != _lastSeenSongId) return;
      lyrics = result;
      _notify();
    } catch (_) {}
  }

  int get activeLyricIndex {
    if (lyrics.isEmpty) return -1;
    final ms = audio.position.inMilliseconds;
    var index = -1;
    for (var i = 0; i < lyrics.length; i++) {
      if (lyrics[i].timeMs <= ms) {
        index = i;
      } else {
        break;
      }
    }
    if (index < 0 && lyrics.first.timeMs < 0) return 0;
    return index;
  }

  String get miniLyric {
    final index = activeLyricIndex;
    if (index >= 0 && index < lyrics.length) return lyrics[index].text;
    return audio.currentSong?.title.isNotEmpty == true
        ? '${audio.currentSong!.title} · ${audio.currentSong!.artist}'
        : '音乐与此刻，恰好相逢';
  }

  String get coverUrl {
    final id = audio.currentSong?.coverId ?? headerCoverId;
    return _api?.coverUrl(id, size: 512) ?? '';
  }

  String playlistCoverUrl(Playlist playlist, {int size = 160}) {
    final local = config.playlistCovers[playlist.id];
    if (local != null) {
      if (local.startsWith('asset:') || File(local).existsSync()) return local;
    }
    return coverUrlFor(playlist.coverId, size: size);
  }

  String get headerCoverUrl {
    final playlist = activePlaylist;
    if (playlist != null) return playlistCoverUrl(playlist, size: 512);
    return coverUrlFor(headerCoverId, size: 512);
  }

  String coverUrlFor(String coverId, {int size = 160}) {
    if (coverId.startsWith('asset:')) return coverId;
    return _api?.coverUrl(coverId, size: size) ?? '';
  }

  void updateWindowSnapshot(WindowSnapshot snapshot) {
    config.window = snapshot;
    _persistSoon();
    _notify();
  }

  void _persistSoon() {
    if (_demoMode) return;
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 500), () {
      ConfigStore.instance.save(config);
    });
  }

  Future<void> shutdown() async {
    _saveTimer?.cancel();
    _positionSaveTimer?.cancel();
    if (!_demoMode) await ConfigStore.instance.save(config);
    await audio.stop();
    _api?.close();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _saveTimer?.cancel();
    _positionSaveTimer?.cancel();
    audio.removeListener(_onAudioChanged);
    audio.positionListenable.removeListener(_onPlaybackProgress);
    actionError.dispose();
    audio.dispose();
    _api?.close();
    super.dispose();
  }
}
