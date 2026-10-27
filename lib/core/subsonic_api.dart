import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';

import 'app_config.dart';
import 'models.dart';

class SubsonicApi {
  SubsonicApi(this.config, {HttpClient? httpClient})
      : _http = httpClient ?? HttpClient() {
    _http.connectionTimeout = const Duration(seconds: 5);
    final salt = _randomSalt();
    _auth = {
      'u': config.username,
      't': md5.convert(utf8.encode('${config.password}$salt')).toString(),
      's': salt,
      'v': '1.16.1',
      'c': 'mup-flutter',
      'f': 'json',
    };
  }

  final AppConfig config;
  final HttpClient _http;
  late final Map<String, String> _auth;
  String? _jellyfinToken;
  String? _jellyfinUserId;
  Map<String, int>? _jellyfinArtistCountCache;

  String get root => '${config.protocol}://${config.host}:${config.port}';
  String get rest => '$root/rest';

  static String _randomSalt() {
    final random = Random.secure();
    return List.generate(
        8, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  }

  Future<bool> ping() async {
    try {
      await _get('ping.view', timeout: const Duration(seconds: 6));
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> _get(
    String view, {
    Map<String, String> parameters = const {},
    Duration timeout = const Duration(seconds: 12),
  }) async {
    final query = <String, String>{..._auth, ...parameters};
    final uri = Uri.parse('$rest/$view').replace(queryParameters: query);
    final request = await _http.getUrl(uri).timeout(timeout);
    request.headers.set(HttpHeaders.userAgentHeader, 'mup-flutter/0.1');
    final response = await request.close().timeout(timeout);
    final text = await utf8.decoder.bind(response).join().timeout(timeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw HttpException('HTTP ${response.statusCode}');
    }
    final decoded = jsonDecode(text);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('服务器返回格式不正确');
    }
    final body =
        (decoded['subsonic-response'] ?? decoded) as Map<String, dynamic>;
    if (body['status'] != 'ok') {
      final error = body['error'];
      final message = error is Map ? error['message'] : null;
      throw HttpException(message?.toString() ?? 'Subsonic 请求失败');
    }
    return body;
  }

  Future<List<Playlist>> getPlaylists() async {
    final body = await _get('getPlaylists.view');
    final playlists = (body['playlists'] as Map?)?['playlist'];
    final result = asList(playlists)
        .whereType<Map>()
        .map((node) => Playlist.fromNode(Map<String, dynamic>.from(node)))
        .where((playlist) => playlist.id.isNotEmpty)
        .toList();
    final favorites = result.where((playlist) => playlist.name.contains('喜欢'));
    final others = result.where((playlist) => !playlist.name.contains('喜欢'));
    return [...favorites, ...others];
  }

  Future<PlaylistSongsResult> getPlaylistSongs(
    String playlistId, {
    bool complete = true,
  }) async {
    const pageSize = 500;
    final songs = <Song>[];
    final seenPages = <String>{};
    var reported = 0;
    var offset = 0;
    while (offset < 20000) {
      final body = await _get(
        'getPlaylist.view',
        parameters: {
          'id': playlistId,
          'offset': '$offset',
          'count': '$pageSize',
        },
      );
      final node = body['playlist'] as Map? ?? const {};
      if (reported == 0) {
        reported = int.tryParse(
              (node['songCount'] ?? node['@songCount'])?.toString() ?? '',
            ) ??
            0;
      }
      final page = asList(node['entry'])
          .whereType<Map>()
          .map((entry) => Song.fromNode(Map<String, dynamic>.from(entry)))
          .where((song) => song.id.isNotEmpty)
          .toList();
      if (page.isEmpty) break;
      final signature = page.map((song) => song.id).join('\u0001');
      if (!seenPages.add(signature)) break;
      songs.addAll(page);
      if (!complete) break;
      if (reported > 0) {
        if (songs.length >= reported) break;
      } else if (page.length < pageSize) {
        break;
      }
      offset += page.length;
    }
    final total = reported > 0 ? reported : songs.length;
    if (!complete || reported <= songs.length) {
      return PlaylistSongsResult(songs: songs, totalCount: total);
    }
    final full = await _getJellyfinPlaylist(playlistId);
    if (full != null && full.length > songs.length) {
      return PlaylistSongsResult(
        songs: full,
        totalCount: max(reported, full.length),
      );
    }
    return PlaylistSongsResult(songs: songs, totalCount: total);
  }

  Future<List<Song>?> _getJellyfinPlaylist(String playlistId) async {
    try {
      if (_jellyfinToken == null || _jellyfinUserId == null) {
        final credentials = await _jellyfinLogin();
        if (credentials == null) return null;
      }
      final songs = <Song>[];
      final seen = <String>{};
      var start = 0;
      while (start < 20000) {
        final uri = Uri.parse('$root/Playlists/fnm-playlist-$playlistId/Items')
            .replace(queryParameters: {
          'userId': _jellyfinUserId!,
          'StartIndex': '$start',
          'Limit': '200',
        });
        final request =
            await _http.getUrl(uri).timeout(const Duration(seconds: 12));
        request.headers.set('X-Emby-Token', _jellyfinToken!);
        final response =
            await request.close().timeout(const Duration(seconds: 12));
        final text = await utf8.decoder
            .bind(response)
            .join()
            .timeout(const Duration(seconds: 12));
        if (response.statusCode < 200 || response.statusCode >= 300) {
          return null;
        }
        final body = jsonDecode(text) as Map<String, dynamic>? ?? const {};
        final items = asList(body['Items']).whereType<Map>().toList();
        if (items.isEmpty) break;
        final before = songs.length;
        for (final item in items) {
          final song = _jellyfinSong(Map<String, dynamic>.from(item));
          if (song.id.isNotEmpty && seen.add(song.id)) songs.add(song);
        }
        final total = (body['TotalRecordCount'] as num?)?.toInt() ?? 0;
        start += items.length;
        if (songs.length == before || (total > 0 && start >= total)) break;
      }
      return songs.where((song) => song.id.isNotEmpty).toList();
    } catch (_) {
      return null;
    }
  }

  Future<(String, String)?> _jellyfinLogin() async {
    try {
      final request = await _http
          .postUrl(Uri.parse('$root/Users/AuthenticateByName'))
          .timeout(const Duration(seconds: 12));
      request.headers.contentType = ContentType.json;
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'MediaBrowser Client="mup-flutter", Device="Windows", DeviceId="mup-flutter-001", Version="0.4.0"',
      );
      request.write(jsonEncode({
        'Username': config.username,
        'Pw': config.password,
      }));
      final response =
          await request.close().timeout(const Duration(seconds: 12));
      final text = await utf8.decoder
          .bind(response)
          .join()
          .timeout(const Duration(seconds: 12));
      final body = jsonDecode(text) as Map<String, dynamic>? ?? const {};
      final token = body['AccessToken']?.toString();
      final user = body['User'];
      final userId = user is Map ? user['Id']?.toString() : null;
      if (token == null || userId == null) return null;
      _jellyfinToken = token;
      _jellyfinUserId = userId;
      return (token, userId);
    } catch (_) {
      return null;
    }
  }

  Future<(String, String)?> _jellyfinReady() async {
    if (_jellyfinToken != null && _jellyfinUserId != null) {
      return (_jellyfinToken!, _jellyfinUserId!);
    }
    return _jellyfinLogin();
  }

  String _stripPrefix(String value, String prefix) =>
      value.startsWith(prefix) ? value.substring(prefix.length) : value;

  Song _jellyfinSong(Map<String, dynamic> item) {
    final artists =
        asList(item['Artists']).whereType<String>().where((e) => e.isNotEmpty);
    final artistItems = asList(item['ArtistItems']).whereType<Map>().toList();
    return Song(
      id: _stripPrefix(item['Id']?.toString() ?? '', 'fnm-track-'),
      title: item['Name']?.toString() ?? '',
      artist: artists.isNotEmpty
          ? artists.join(', ')
          : item['AlbumArtist']?.toString() ?? '',
      artistId: artistItems.isEmpty
          ? ''
          : _stripPrefix(
              artistItems.first['Id']?.toString() ?? '',
              'fnm-artist-',
            ),
      album: item['Album']?.toString() ?? '',
      albumId: _stripPrefix(item['AlbumId']?.toString() ?? '', 'fnm-album-'),
      duration: ((item['RunTimeTicks'] as num?)?.toInt() ?? 0) ~/ 10000000,
      coverId: item['Id']?.toString() ?? '',
    );
  }

  Future<List<Album>> getAlbums({
    String type = 'newest',
    int size = 500,
  }) async {
    final albums = <Album>[];
    final seen = <String>{};
    var offset = 0;
    while (offset < 20000) {
      final body = await _get(
        'getAlbumList2.view',
        parameters: {
          'type': type,
          'size': '$size',
          'offset': '$offset',
        },
      );
      final nodes = (body['albumList2'] as Map?)?['album'];
      final page = asList(nodes)
          .whereType<Map>()
          .map((node) => Album.fromNode(Map<String, dynamic>.from(node)))
          .where((album) => album.id.isNotEmpty)
          .toList();
      if (page.isEmpty) break;
      final before = albums.length;
      for (final album in page) {
        if (seen.add(album.id)) albums.add(album);
      }
      if (albums.length == before) break;
      offset += page.length;
    }
    return albums;
  }

  Future<List<Song>> getAlbum(String albumId) async {
    final body = await _get('getAlbum.view', parameters: {'id': albumId});
    final songs = (body['album'] as Map?)?['song'];
    return asList(songs)
        .whereType<Map>()
        .map((node) => Song.fromNode(Map<String, dynamic>.from(node)))
        .toList();
  }

  Future<List<Artist>> getArtists() async {
    final body = await _get('getArtists.view');
    final collection = body['artists'] as Map?;
    final indexes = collection?['index'];
    final result = <Artist>[];
    for (final index in asList(indexes).whereType<Map>()) {
      for (final node in asList(index['artist']).whereType<Map>()) {
        result.add(Artist.fromNode(Map<String, dynamic>.from(node)));
      }
    }
    if (result.isEmpty) {
      for (final node in asList(collection?['artist']).whereType<Map>()) {
        result.add(Artist.fromNode(Map<String, dynamic>.from(node)));
      }
    }
    return result;
  }

  Future<Map<String, int>> getArtistSongCounts(List<Artist> artists) async {
    final exact = await _getJellyfinArtistCounts();
    if (exact != null) {
      return {
        for (final artist in artists) artist.id: exact[artist.id] ?? 0,
      };
    }
    final counts = <String, int>{};
    final seenAlbums = <String>{};
    for (final type in const [
      'newest',
      'alphabeticalByName',
      'alphabeticalByArtist',
    ]) {
      try {
        final albums = await getAlbums(type: type, size: 500);
        for (final album in albums) {
          if (album.artistId.isEmpty) continue;
          if (album.id.isNotEmpty && !seenAlbums.add(album.id)) continue;
          counts[album.artistId] =
              (counts[album.artistId] ?? 0) + album.songCount;
        }
      } catch (_) {}
    }
    return {for (final artist in artists) artist.id: counts[artist.id] ?? 0};
  }

  Future<Map<String, int>?> _getJellyfinArtistCounts() async {
    if (_jellyfinArtistCountCache != null) return _jellyfinArtistCountCache;
    final credentials = await _jellyfinReady();
    if (credentials == null) return null;
    final counts = <String, int>{};
    final seenSongs = <String>{};
    var start = 0;
    while (start < 20000) {
      final uri = Uri.parse('$root/Items').replace(queryParameters: {
        'userId': _jellyfinUserId!,
        'Recursive': 'true',
        'IncludeItemTypes': 'Audio',
        'StartIndex': '$start',
        'Limit': '500',
        'Fields': 'Artists,ArtistItems',
        'EnableImages': 'false',
      });
      final request =
          await _http.getUrl(uri).timeout(const Duration(seconds: 12));
      request.headers.set('X-Emby-Token', _jellyfinToken!);
      final response =
          await request.close().timeout(const Duration(seconds: 12));
      final text = await utf8.decoder
          .bind(response)
          .join()
          .timeout(const Duration(seconds: 12));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return null;
      }
      final body = jsonDecode(text) as Map<String, dynamic>? ?? const {};
      final items = asList(body['Items']).whereType<Map>().toList();
      if (items.isEmpty) break;
      for (final raw in items) {
        final item = Map<String, dynamic>.from(raw);
        final songId = item['Id']?.toString() ?? '';
        if (songId.isNotEmpty && !seenSongs.add(songId)) continue;
        final ids = <String>{};
        for (final artist in asList(
          item['ArtistItems'],
        ).whereType<Map>()) {
          final id = _stripPrefix(
            artist['Id']?.toString() ?? '',
            'fnm-artist-',
          );
          if (id.isNotEmpty) ids.add(id);
        }
        for (final id in ids) {
          counts[id] = (counts[id] ?? 0) + 1;
        }
      }
      start += items.length;
      final total = (body['TotalRecordCount'] as num?)?.toInt() ?? 0;
      if (total > 0 && start >= total) break;
    }
    return _jellyfinArtistCountCache = counts;
  }

  Future<List<Album>> getArtistAlbums(String artistId) async {
    final body = await _get('getArtist.view', parameters: {'id': artistId});
    final albums = (body['artist'] as Map?)?['album'];
    return asList(albums)
        .whereType<Map>()
        .map((node) => Album.fromNode(Map<String, dynamic>.from(node)))
        .toList();
  }

  Future<List<Song>> getArtistSongs(String artistId) async {
    final jellyfin = await _getJellyfinArtistSongs(artistId);
    if (jellyfin != null) return jellyfin;
    final albums = await getArtistAlbums(artistId);
    final songs = <Song>[];
    final seen = <String>{};
    for (final album in albums) {
      try {
        for (final song in await getAlbum(album.id)) {
          if (seen.add(song.id)) songs.add(song);
        }
      } catch (_) {
        continue;
      }
    }
    return songs;
  }

  Future<List<Song>?> _getJellyfinArtistSongs(String artistId) async {
    final credentials = await _jellyfinReady();
    if (credentials == null) return null;
    final songs = <Song>[];
    final seen = <String>{};
    var start = 0;
    while (start < 20000) {
      final uri = Uri.parse('$root/Items').replace(queryParameters: {
        'userId': _jellyfinUserId!,
        'ArtistIds': 'fnm-artist-$artistId',
        'Recursive': 'true',
        'IncludeItemTypes': 'Audio',
        'StartIndex': '$start',
        'Limit': '500',
        'Fields': 'Artists,ArtistItems',
        'EnableImages': 'false',
      });
      final request =
          await _http.getUrl(uri).timeout(const Duration(seconds: 12));
      request.headers.set('X-Emby-Token', _jellyfinToken!);
      final response =
          await request.close().timeout(const Duration(seconds: 12));
      final text = await utf8.decoder
          .bind(response)
          .join()
          .timeout(const Duration(seconds: 12));
      if (response.statusCode < 200 || response.statusCode >= 300) return null;
      final body = jsonDecode(text) as Map<String, dynamic>? ?? const {};
      final items = asList(body['Items']).whereType<Map>().toList();
      if (items.isEmpty) break;
      final before = songs.length;
      for (final item in items) {
        final song = _jellyfinSong(Map<String, dynamic>.from(item));
        if (song.id.isNotEmpty && seen.add(song.id)) songs.add(song);
      }
      start += items.length;
      final total = (body['TotalRecordCount'] as num?)?.toInt() ?? 0;
      if (songs.length == before || (total > 0 && start >= total)) break;
    }
    return songs.where((song) => song.id.isNotEmpty).toList();
  }

  Future<List<Song>> getStarred() async {
    final body = await _get('getStarred2.view');
    final songs = (body['starred2'] as Map?)?['song'];
    return asList(songs)
        .whereType<Map>()
        .map((node) => Song.fromNode(
              Map<String, dynamic>.from(node),
            ).withStarred(true))
        .toList();
  }

  Future<void> setStarred(String songId, bool value) async {
    await _get(value ? 'star.view' : 'unstar.view', parameters: {'id': songId});
  }

  Future<List<Song>> getRecentlyPlayed() async {
    final body = await _get('getPlayQueue.view');
    final songs = (body['playQueue'] as Map?)?['entry'];
    return asList(songs)
        .whereType<Map>()
        .map((node) => Song.fromNode(Map<String, dynamic>.from(node)))
        .toList();
  }

  Future<(List<Song>, List<Album>, List<Artist>)> search(String query) async {
    final body = await _get('search3.view', parameters: {
      'query': query,
      'songCount': '200',
      'albumCount': '60',
      'artistCount': '60',
    });
    final result = body['searchResult3'] as Map? ?? const {};
    List<T> parse<T>(String key, T Function(Map<String, dynamic>) convert) =>
        asList(result[key])
            .whereType<Map>()
            .map((node) => convert(Map<String, dynamic>.from(node)))
            .toList();
    return (
      parse('song', Song.fromNode),
      parse('album', Album.fromNode),
      parse('artist', Artist.fromNode),
    );
  }

  Future<List<LyricLine>> getLyrics(Song song) async {
    try {
      final body = await _get(
        'getLyricsBySongId.view',
        parameters: {'id': song.id},
      );
      final list = body['lyricsList'] as Map? ?? const {};
      final lines = <LyricLine>[];
      for (final structured
          in asList(list['structuredLyrics']).whereType<Map>()) {
        for (final node in asList(structured['line']).whereType<Map>()) {
          final text = node['value']?.toString() ?? '';
          if (text.isEmpty) continue;
          lines.add(LyricLine(
            int.tryParse(node['start']?.toString() ?? '') ?? -1,
            text,
          ));
        }
      }
      if (lines.isNotEmpty) return lines;
    } catch (_) {}
    try {
      final body = await _get('getLyrics.view', parameters: {
        'artist': song.artist,
        'title': song.title,
      });
      final raw = (body['lyrics'] as Map?)?['lyric']?.toString() ?? '';
      return _parseLrc(raw);
    } catch (_) {
      return const [];
    }
  }

  List<LyricLine> _parseLrc(String raw) {
    final pattern = RegExp(r'\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]');
    final result = <LyricLine>[];
    for (final source in raw.split('\n')) {
      final matches = pattern.allMatches(source).toList();
      final text = source.replaceAll(pattern, '').trim();
      if (text.isEmpty) continue;
      if (matches.isEmpty) {
        result.add(LyricLine(-1, text));
        continue;
      }
      for (final match in matches) {
        final minutes = int.parse(match.group(1)!);
        final seconds = int.parse(match.group(2)!);
        final fraction = match.group(3) ?? '';
        final milli = fraction.isEmpty
            ? 0
            : int.parse(fraction.padRight(3, '0').substring(0, 3));
        result.add(LyricLine((minutes * 60 + seconds) * 1000 + milli, text));
      }
    }
    result.sort((a, b) => a.timeMs.compareTo(b.timeMs));
    return result;
  }

  String streamUrl(String songId) {
    return Uri.parse('$rest/stream.view')
        .replace(queryParameters: {..._auth, 'id': songId}).toString();
  }

  String coverUrl(String coverId, {int size = 160}) {
    if (coverId.isEmpty) return '';
    if (coverId.startsWith('fnm-')) {
      return '$root/Items/$coverId/Images/Primary?maxHeight=$size&maxWidth=$size';
    }
    return Uri.parse('$rest/getCoverArt.view').replace(
        queryParameters: {..._auth, 'id': coverId, 'size': '$size'}).toString();
  }

  void close() => _http.close(force: true);
}
