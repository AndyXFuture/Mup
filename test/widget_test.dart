import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mup_flutter/core/app_config.dart';
import 'package:mup_flutter/core/app_controller.dart';
import 'package:mup_flutter/core/audio_controller.dart';
import 'package:mup_flutter/core/models.dart';
import 'package:mup_flutter/core/secret_protection.dart';
import 'package:mup_flutter/core/subsonic_api.dart';
import 'package:mup_flutter/core/window_bounds.dart';
import 'package:mup_flutter/ui/pages/library_page.dart';
import 'package:mup_flutter/ui/theme.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = null;

  test('默认端口为 14040', () {
    expect(AppConfig().port, 14040);
  });

  test('兼容音桥与标准 Subsonic 字段', () {
    final bridge = Song.fromNode({
      'id': 'song-1',
      'title': '旅行家说',
      'artistId': 'artist-1',
      'albumId': 'album-1',
    });
    final standard = Song.fromNode({
      '@id': 'song-2',
      '@title': '平凡之路',
    });

    expect(bridge.title, '旅行家说');
    expect(bridge.artistId, 'artist-1');
    expect(standard.title, '平凡之路');
  });

  test('歌曲收藏状态可序列化且不会被普通专辑结果误标', () {
    final song = Song.fromNode({
      'id': 'song-1',
      'title': '旅行家说',
      'starred': '2026-10-27T12:00:00Z',
    });

    expect(song.starred, isTrue);
    expect(Song.fromJson(song.toJson()).starred, isTrue);
    expect(song.withStarred(false).starred, isFalse);
    expect(Song.fromNode({'id': 'song-2'}).starred, isFalse);
  });

  test('配置可保留窗口、侧边栏与自定义封面', () {
    final config = AppConfig(
      host: 'music.example.com',
      username: 'listener',
      password: 'example-password',
      sidebarWidth: 236,
      window: const WindowSnapshot(
        x: 0,
        y: 0,
        width: 1200,
        height: 760,
        hasPosition: true,
      ),
      recentSongs: const [
        Song(id: 'recent-1', title: '最近播放的歌曲'),
      ],
    )..playlistCovers['favorites'] = 'example-covers/favorites.png';

    final restored = AppConfig.fromJson(config.toJson());

    expect(restored.port, 14040);
    expect(restored.sidebarWidth, 236);
    expect(restored.window.hasPosition, isTrue);
    expect(restored.window.x, 0);
    expect(restored.recentSongs.single.id, 'recent-1');
    expect(
        restored.playlistCovers['favorites'], 'example-covers/favorites.png');
  });

  test('Windows DPAPI 可加密并还原服务器密码', () {
    if (!Platform.isWindows) return;
    const password = 'local-test-secret';

    final protected = SecretProtection.protectSecret(password);

    expect(protected, isNot(contains(password)));
    expect(SecretProtection.unprotectSecret(protected), password);
  });

  test('密码解密失败时保留其余本地配置', () {
    final restored = AppConfig.fromJson({
      'host': 'music.example.com',
      'username': 'listener',
      'password': 'not-valid-dpapi-data',
      'passwordProtected': true,
      'themeMode': 'light',
      'sidebarWidth': 226,
    });

    expect(restored.host, 'music.example.com');
    expect(restored.username, 'listener');
    expect(restored.password, isEmpty);
    expect(restored.themeMode, 'light');
    expect(restored.sidebarWidth, 226);
  });

  test('音桥流地址包含歌曲 ID', () {
    final api = SubsonicApi(AppConfig(
      host: 'music.example.com',
      username: 'listener',
      password: 'example-password',
    ));
    expect(api.streamUrl('song id'), contains('id=song+id'));
    api.close();
  });

  test('屏幕外的恢复位置会回到主显示器可见区域', () {
    const primary = Rect.fromLTWH(0, 0, 1920, 1040);
    const hidden = Rect.fromLTWH(-32000, -32000, 980, 622);

    expect(repairWindowBounds(hidden, [primary]), isNot(hidden));
    expect(repairWindowBounds(hidden, [primary]).center, primary.center);
  });

  test('跨屏但仍然可见的窗口位置保持不变', () {
    const displays = [
      Rect.fromLTWH(0, 0, 1920, 1040),
      Rect.fromLTWH(1920, 0, 1920, 1040),
    ];
    const window = Rect.fromLTWH(1800, 100, 800, 600);

    expect(repairWindowBounds(window, displays), window);
  });

  test('歌单分页在服务器限制单页数量时仍能完整读取', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    final entries = [
      {'id': 's1', 'title': '第一首'},
      {'id': 's2', 'title': '第二首'},
      {'id': 's3', 'title': '第三首'},
    ];
    server.listen((request) async {
      final offset =
          int.tryParse(request.uri.queryParameters['offset'] ?? '') ?? 0;
      final page = entries.skip(offset).take(2).toList();
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({
        'subsonic-response': {
          'status': 'ok',
          'playlist': {'songCount': entries.length, 'entry': page},
        },
      }));
      await request.response.close();
    });
    final api = SubsonicApi(
        AppConfig(
          host: InternetAddress.loopbackIPv4.address,
          port: server.port,
          username: 'listener',
          password: 'example-password',
        ),
        httpClient: HttpClient()..findProxy = (_) => 'DIRECT');
    addTearDown(api.close);

    final result = await api.getPlaylistSongs('playlist-1');

    expect(result.songs.map((song) => song.id), ['s1', 's2', 's3']);
    expect(result.totalCount, 3);
  });

  test('歌单中重复出现的歌曲不会导致数量减少', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((request) async {
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({
        'subsonic-response': {
          'status': 'ok',
          'playlist': {
            'songCount': 3,
            'entry': [
              {'id': 's1', 'title': '第一首'},
              {'id': 's1', 'title': '第一首'},
              {'id': 's2', 'title': '第二首'},
            ],
          },
        },
      }));
      await request.response.close();
    });
    final api = SubsonicApi(
      AppConfig(
        host: InternetAddress.loopbackIPv4.address,
        port: server.port,
        username: 'listener',
        password: 'example-password',
      ),
      httpClient: HttpClient()..findProxy = (_) => 'DIRECT',
    );
    addTearDown(api.close);

    final result = await api.getPlaylistSongs('playlist-1');

    expect(result.songs.map((song) => song.id), ['s1', 's1', 's2']);
    expect(result.totalCount, 3);
  });

  test('歌手统计在三种排序中不会重复累加同一张专辑', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    server.listen((request) async {
      request.response.headers.contentType = ContentType.json;
      if (request.uri.path.endsWith('/Users/AuthenticateByName')) {
        request.response.statusCode = HttpStatus.unauthorized;
        request.response.write('{}');
      } else {
        request.response.write(jsonEncode({
          'subsonic-response': {
            'status': 'ok',
            'albumList2': {
              'album': [
                {
                  'id': 'album-1',
                  'name': '示例专辑',
                  'artistId': 'artist-1',
                  'songCount': 10,
                },
              ],
            },
          },
        }));
      }
      await request.response.close();
    });
    final api = SubsonicApi(
        AppConfig(
          host: InternetAddress.loopbackIPv4.address,
          port: server.port,
          username: 'listener',
          password: 'example-password',
        ),
        httpClient: HttpClient()..findProxy = (_) => 'DIRECT');
    addTearDown(api.close);

    final counts = await api.getArtistSongCounts(const [
      Artist(id: 'artist-1', name: '示例歌手'),
    ]);

    expect(counts['artist-1'], 10);
  });

  test('播放队列补全遇到不包含当前歌曲的列表时拒绝替换', () {
    final audio = MupAudioController();
    addTearDown(audio.dispose);
    audio.restoreQueue(
      const [Song(id: 'current', title: '当前歌曲')],
      preferredSongId: 'current',
      queueKey: 'playlist:a',
    );

    final replaced = audio.replaceQueueKeepingCurrent(
      const [Song(id: 'other', title: '其他歌曲')],
      queueKey: 'playlist:b',
    );

    expect(replaced, isFalse);
    expect(audio.queue.single.id, 'current');
    expect(audio.currentSong?.id, 'current');
    expect(audio.playbackQueueKey, 'playlist:a');
  });

  test('恢复播放队列时同步恢复进度条位置', () {
    final audio = MupAudioController();
    addTearDown(audio.dispose);

    audio.restoreQueue(
      const [Song(id: 'song-1', title: '第一首', duration: 180)],
      preferredSongId: 'song-1',
      positionMs: 61123,
    );

    expect(audio.position.inMilliseconds, 61123);
    expect(audio.positionListenable.value.inMilliseconds, 61123);
  });

  test('专辑列表分页在服务器降低单页上限时仍能完整读取', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    final entries = [
      {'id': 'a1', 'name': '第一张'},
      {'id': 'a2', 'name': '第二张'},
      {'id': 'a3', 'name': '第三张'},
    ];
    server.listen((request) async {
      final offset =
          int.tryParse(request.uri.queryParameters['offset'] ?? '') ?? 0;
      final page = entries.skip(offset).take(2).toList();
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({
        'subsonic-response': {
          'status': 'ok',
          'albumList2': {'album': page},
        },
      }));
      await request.response.close();
    });
    final api = SubsonicApi(
        AppConfig(
          host: InternetAddress.loopbackIPv4.address,
          port: server.port,
          username: 'listener',
          password: 'example-password',
        ),
        httpClient: HttpClient()..findProxy = (_) => 'DIRECT');
    addTearDown(api.close);

    final albums = await api.getAlbums();

    expect(albums.map((album) => album.id), ['a1', 'a2', 'a3']);
  });

  testWidgets('未提交的搜索草稿不会被后台状态刷新覆盖', (tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = AppController()..prepareDemo();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      MaterialApp(
        theme: MupTheme.material(true),
        home: Scaffold(
          body: AnimatedBuilder(
            animation: controller,
            builder: (context, _) => LibraryPage(controller: controller),
          ),
        ),
      ),
    );
    await tester.pump();

    final search = find.byType(TextField).first;
    await tester.enterText(search, '尚未提交的搜索词');
    controller.setCompact(true);
    await tester.pump();

    final field = tester.widget<TextField>(search);
    expect(field.controller?.text, '尚未提交的搜索词');
    await tester.pump(const Duration(seconds: 3));
  });
}
