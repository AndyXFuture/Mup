class Song {
  const Song({
    required this.id,
    required this.title,
    this.artist = '',
    this.artistId = '',
    this.album = '',
    this.albumId = '',
    this.duration = 0,
    this.coverId = '',
    this.track = 0,
    this.year = 0,
  });

  final String id;
  final String title;
  final String artist;
  final String artistId;
  final String album;
  final String albumId;
  final int duration;
  final String coverId;
  final int track;
  final int year;

  String get subtitle => [artist, album].where((e) => e.isNotEmpty).join(' · ');

  factory Song.fromNode(Map<String, dynamic> node) {
    return Song(
      id: _text(node, 'id', '@id'),
      title: _text(node, 'title', '@title', '#text'),
      artist: _text(node, 'artist', '@artist'),
      artistId: _text(node, 'artistId', '@artistId'),
      album: _text(node, 'album', '@album'),
      albumId: _text(node, 'albumId', '@albumId'),
      duration: _integer(node, 'duration', '@duration'),
      coverId: _text(node, 'coverArt', '@coverArt'),
      track: _integer(node, 'track', '@track'),
      year: _integer(node, 'year', '@year'),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'artist': artist,
        'artistId': artistId,
        'album': album,
        'albumId': albumId,
        'duration': duration,
        'coverId': coverId,
        'track': track,
        'year': year,
      };

  factory Song.fromJson(Map<String, dynamic> json) => Song(
        id: json['id']?.toString() ?? '',
        title: json['title']?.toString() ?? '',
        artist: json['artist']?.toString() ?? '',
        artistId: json['artistId']?.toString() ?? '',
        album: json['album']?.toString() ?? '',
        albumId: json['albumId']?.toString() ?? '',
        duration: (json['duration'] as num?)?.toInt() ?? 0,
        coverId: json['coverId']?.toString() ?? '',
        track: (json['track'] as num?)?.toInt() ?? 0,
        year: (json['year'] as num?)?.toInt() ?? 0,
      );
}

class Playlist {
  const Playlist({
    required this.id,
    required this.name,
    this.songCount = 0,
    this.duration = 0,
    this.coverId = '',
    this.comment = '',
  });

  final String id;
  final String name;
  final int songCount;
  final int duration;
  final String coverId;
  final String comment;

  factory Playlist.fromNode(Map<String, dynamic> node) => Playlist(
        id: _text(node, 'id', '@id'),
        name: _text(node, 'name', '@name'),
        songCount: _integer(node, 'songCount', '@songCount'),
        duration: _integer(node, 'duration', '@duration'),
        coverId: _text(node, 'coverArt', '@coverArt'),
        comment: _text(node, 'comment', '@comment'),
      );
}

class Album {
  const Album({
    required this.id,
    required this.name,
    this.artist = '',
    this.artistId = '',
    this.coverId = '',
    this.songCount = 0,
  });

  final String id;
  final String name;
  final String artist;
  final String artistId;
  final String coverId;
  final int songCount;

  factory Album.fromNode(Map<String, dynamic> node) => Album(
        id: _text(node, 'id', '@id'),
        name: _text(node, 'name', '@name'),
        artist: _text(node, 'artist', '@artist'),
        artistId: _text(node, 'artistId', '@artistId'),
        coverId: _text(node, 'coverArt', '@coverArt'),
        songCount: _integer(node, 'songCount', '@songCount'),
      );
}

class Artist {
  const Artist({
    required this.id,
    required this.name,
    this.coverId = '',
    this.albumCount = 0,
    this.songCount = 0,
  });

  final String id;
  final String name;
  final String coverId;
  final int albumCount;
  final int songCount;

  factory Artist.fromNode(Map<String, dynamic> node) => Artist(
        id: _text(node, 'id', '@id'),
        name: _text(node, 'name', '@name'),
        coverId: _text(node, 'coverArt', '@coverArt'),
        albumCount: _integer(node, 'albumCount', '@albumCount'),
      );

  Artist withSongCount(int value) => Artist(
        id: id,
        name: name,
        coverId: coverId,
        albumCount: albumCount,
        songCount: value,
      );
}

class LyricLine {
  const LyricLine(this.timeMs, this.text);

  final int timeMs;
  final String text;
}

String _text(Map<String, dynamic> node, String first,
    [String? second, String? third]) {
  for (final key in [first, second, third]) {
    if (key != null && node[key] != null) return node[key].toString();
  }
  return '';
}

int _integer(Map<String, dynamic> node, String first, [String? second]) {
  for (final key in [first, second]) {
    if (key == null) continue;
    final value = node[key];
    if (value is num) return value.toInt();
    if (value != null) return int.tryParse(value.toString()) ?? 0;
  }
  return 0;
}

List<dynamic> asList(dynamic value) {
  if (value == null) return const [];
  return value is List ? value : [value];
}
