import 'package:flutter_test/flutter_test.dart';
import 'package:mup_flutter/core/app_config.dart';
import 'package:mup_flutter/core/models.dart';
import 'package:mup_flutter/core/subsonic_api.dart';

void main() {
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

  test('配置可保留窗口、侧边栏与自定义封面', () {
    final config = AppConfig(
      host: 'music.example.com',
      username: 'listener',
      password: 'example-password',
      sidebarWidth: 236,
    )..playlistCovers['favorites'] = 'example-covers/favorites.png';

    final restored = AppConfig.fromJson(config.toJson());

    expect(restored.port, 14040);
    expect(restored.sidebarWidth, 236);
    expect(restored.playlistCovers['favorites'], 'example-covers/favorites.png');
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
}
