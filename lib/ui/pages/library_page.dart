import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../../core/app_controller.dart';
import '../../core/audio_controller.dart';
import '../../core/models.dart';
import '../components/controls.dart';
import '../components/cover_art.dart';
import '../theme.dart';
import '../widgets/playback_bar.dart';
import '../widgets/sidebar.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key, required this.controller});

  final AppController controller;

  @override
  State<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends State<LibraryPage> {
  late final TextEditingController _search = TextEditingController(
    text: widget.controller.searchQuery,
  );
  late final FocusNode _searchFocus = FocusNode();
  late double _sidebarWidth =
      widget.controller.config.sidebarWidth.clamp(180, 300);
  double _dragWidth = 0;

  @override
  void dispose() {
    _search.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  void _focusSearch() {
    _searchFocus.requestFocus();
    _search.selection =
        TextSelection(baseOffset: 0, extentOffset: _search.text.length);
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return Shortcuts(
      shortcuts: const {
        SingleActivator(LogicalKeyboardKey.keyF, control: true):
            _FocusSearchIntent(),
      },
      child: Actions(
        actions: {
          _FocusSearchIntent: CallbackAction<_FocusSearchIntent>(
            onInvoke: (_) {
              _focusSearch();
              return null;
            },
          ),
        },
        child: Focus(
          autofocus: true,
          child: Column(
            children: [
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 0),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      SizedBox(
                        width: _sidebarWidth,
                        child: Stack(
                          clipBehavior: Clip.none,
                          children: [
                            Positioned.fill(
                              child: Sidebar(
                                controller: controller,
                                searchController: _search,
                                searchFocusNode: _searchFocus,
                                width: _sidebarWidth,
                              ),
                            ),
                            Positioned(
                              top: 12,
                              bottom: 12,
                              right: -8,
                              width: 12,
                              child: MouseRegion(
                                cursor: SystemMouseCursors.resizeColumn,
                                child: GestureDetector(
                                  behavior: HitTestBehavior.translucent,
                                  onHorizontalDragStart: (_) {
                                    _dragWidth = _sidebarWidth;
                                  },
                                  onHorizontalDragUpdate: (details) {
                                    setState(() {
                                      _sidebarWidth =
                                          (_dragWidth + details.primaryDelta!)
                                              .clamp(180, 300);
                                      _dragWidth = _sidebarWidth;
                                    });
                                  },
                                  onHorizontalDragEnd: (_) {
                                    controller.setSidebarWidth(_sidebarWidth);
                                  },
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(child: _Content(controller: controller)),
                    ],
                  ),
                ),
              ),
              _MiniLyrics(controller: controller),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: PlaybackBar(controller: controller),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FocusSearchIntent extends Intent {
  const _FocusSearchIntent();
}

class _Content extends StatelessWidget {
  const _Content({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: theme.dark
              ? [const Color(0x08000000), const Color(0x21000000)]
              : [
                  Colors.white.withValues(alpha: 0.70),
                  Colors.white.withValues(alpha: 0.45)
                ],
        ),
        border: Border.all(
          color: theme.dark
              ? Colors.white.withValues(alpha: 0.045)
              : Colors.white.withValues(alpha: 0.68),
        ),
        boxShadow: [
          BoxShadow(
            color: theme.shadow.withValues(alpha: theme.dark ? 0.2 : 0.10),
            blurRadius: 30,
            spreadRadius: -22,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(18),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Header(controller: controller),
              const SizedBox(height: 7),
              _ListHeader(controller: controller),
              Expanded(child: _Body(controller: controller)),
            ],
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        CoverArt(
          url: controller.headerCoverUrl,
          size: 96,
          radius: 18,
          glow: true,
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                controller.contentTitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: theme.text,
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.2,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                controller.contentSubtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: theme.muted, fontSize: 12),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  if (controller.songs.isNotEmpty) ...[
                    MupTextButton(
                      label: '播放全部',
                      icon: LucideIcons.play,
                      primary: true,
                      onTap: () => controller.playAll(),
                    ),
                    const SizedBox(width: 10),
                    MupTextButton(
                      label: '随机播放',
                      icon: LucideIcons.shuffle,
                      onTap: () => controller.playAll(shuffle: true),
                    ),
                    const SizedBox(width: 10),
                  ],
                  MupTextButton(
                    label: '',
                    icon: LucideIcons.rotateCw,
                    iconOnly: true,
                    onTap: controller.refreshCurrent,
                  ),
                  if (controller.activePlaylist != null) ...[
                    const SizedBox(width: 10),
                    Builder(
                      builder: (menuContext) => MupTextButton(
                        label: '',
                        icon: LucideIcons.pencil,
                        iconOnly: true,
                        onTap: () => _showCoverMenu(menuContext, controller),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _showCoverMenu(
    BuildContext context,
    AppController controller,
  ) async {
    final overlay = Overlay.of(context).context.findRenderObject() as RenderBox;
    final box = context.findRenderObject() as RenderBox;
    final origin = box.localToGlobal(Offset.zero, ancestor: overlay);
    final action = await showMenu<String>(
      context: context,
      color: MupTheme.of(context).surfaceBottom,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      position: RelativeRect.fromLTRB(
        origin.dx,
        origin.dy + box.size.height,
        overlay.size.width - origin.dx - box.size.width,
        overlay.size.height - origin.dy,
      ),
      items: const [
        PopupMenuItem(value: 'local', child: Text('选择本地图片…')),
        PopupMenuItem(value: 'server', child: Text('使用服务器封面')),
      ],
    );
    if (action == 'local') {
      await controller.choosePlaylistCover();
    } else if (action == 'server') {
      await controller.useServerPlaylistCover();
    }
  }
}

class _ListHeader extends StatelessWidget {
  const _ListHeader({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final count = controller.activeNav == 'search'
        ? controller.songs.length
        : controller.albums.isNotEmpty
            ? controller.albums.length
            : controller.artists.length;
    return Container(
      height: 26,
      padding: const EdgeInsets.only(left: 72, right: 8),
      child: Row(
        children: [
          Text(
            controller.activeNav == 'search' && controller.songs.isNotEmpty
                ? '歌名 / 歌手'
                : controller.albums.isNotEmpty
                    ? '专辑'
                    : controller.artists.isNotEmpty
                        ? '歌手'
                        : '歌名 / 歌手',
            style: TextStyle(color: theme.dim, fontSize: 11),
          ),
          const Spacer(),
          if (controller.albums.isEmpty && controller.artists.isEmpty) ...[
            const SizedBox(width: 180),
            const SizedBox(width: 64),
          ] else
            Text('$count 项', style: TextStyle(color: theme.dim, fontSize: 11)),
        ],
      ),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    if (controller.loading) {
      return const Center(
        child: SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 1.6),
        ),
      );
    }
    if (controller.contentError != null && controller.songs.isEmpty) {
      return Center(
        child: Text(
          controller.contentError!,
          textAlign: TextAlign.center,
          style: TextStyle(color: MupTheme.of(context).muted, fontSize: 12),
        ),
      );
    }
    if (controller.activeNav == 'search' && controller.songs.isNotEmpty) {
      return _songList(controller);
    }
    if (controller.albums.isNotEmpty) {
      return _AlbumGrid(controller: controller);
    }
    if (controller.artists.isNotEmpty) {
      return _ArtistList(controller: controller);
    }
    return _songList(controller);
  }

  Widget _songList(AppController controller) {
    return ScrollConfiguration(
      behavior: const _NoOverscrollBehavior(),
      child: ListView.builder(
        padding: const EdgeInsets.only(bottom: 4),
        itemCount: controller.songs.length,
        itemBuilder: (context, index) => _SongRow(
          controller: controller,
          song: controller.songs[index],
        ),
      ),
    );
  }
}

class _SongRow extends StatefulWidget {
  const _SongRow({required this.controller, required this.song});

  final AppController controller;
  final Song song;

  @override
  State<_SongRow> createState() => _SongRowState();
}

class _SongRowState extends State<_SongRow> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final controller = widget.controller;
    final song = widget.song;
    final current = controller.audio.currentSong?.id == song.id;
    final playing =
        current && controller.audio.state == MupPlaybackState.playing;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => controller.playSong(song),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 170),
          height: 64,
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            color: current ? null : (_hover ? theme.track : Colors.transparent),
            gradient: current
                ? LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      theme.primary.withValues(alpha: 0.15),
                      theme.primary.withValues(alpha: 0.06),
                    ],
                  )
                : null,
            border: Border(
              bottom: BorderSide(color: theme.separator, width: 0.7),
            ),
          ),
          child: Row(
            children: [
              Stack(
                alignment: Alignment.center,
                children: [
                  CoverArt(
                    url: controller.coverUrlFor(song.coverId, size: 96),
                    size: 48,
                    radius: 12,
                  ),
                  AnimatedOpacity(
                    opacity: _hover ? 1 : 0,
                    duration: const Duration(milliseconds: 150),
                    child: Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.28),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        playing ? LucideIcons.pause : LucideIcons.play,
                        size: 16,
                        color: Colors.white,
                        fill: playing ? 0 : 1,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        if (current)
                          Padding(
                            padding: const EdgeInsets.only(right: 6),
                            child: _EqBars(active: playing),
                          ),
                        Expanded(
                          child: Text(
                            song.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: current ? theme.primaryText : theme.text,
                              fontSize: 13,
                              fontWeight:
                                  current ? FontWeight.w600 : FontWeight.w400,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    _LinkText(
                      text: song.artist.isEmpty ? '未知歌手' : song.artist,
                      color: theme.muted,
                      onTap: song.artistId.isEmpty
                          ? null
                          : () => controller.openArtist(song),
                    ),
                  ],
                ),
              ),
              SizedBox(
                width: 180,
                child: _LinkText(
                  text: song.album.isEmpty ? '未知专辑' : song.album,
                  color: theme.muted,
                  onTap: song.albumId.isEmpty
                      ? null
                      : () => controller.openAlbum(song),
                ),
              ),
              SizedBox(
                width: 64,
                child: Text(
                  _formatDuration(song.duration),
                  style: TextStyle(
                    color: theme.muted,
                    fontSize: 12,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatDuration(int seconds) =>
      '${(seconds ~/ 60).toString().padLeft(2, '0')}:${(seconds % 60).toString().padLeft(2, '0')}';
}

class _LinkText extends StatefulWidget {
  const _LinkText({required this.text, required this.color, this.onTap});

  final String text;
  final Color color;
  final VoidCallback? onTap;

  @override
  State<_LinkText> createState() => _LinkTextState();
}

class _LinkTextState extends State<_LinkText> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        child: GestureDetector(
          onTap: widget.onTap,
          child: Text(
            widget.text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: _hover ? theme.primaryText : widget.color,
              fontSize: 11.5,
              decoration:
                  _hover ? TextDecoration.underline : TextDecoration.none,
              decorationColor: theme.primaryLight,
            ),
          ),
        ),
      ),
    );
  }
}

class _EqBars extends StatefulWidget {
  const _EqBars({required this.active});

  final bool active;

  @override
  State<_EqBars> createState() => _EqBarsState();
}

class _EqBarsState extends State<_EqBars> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 800),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final phase = widget.active ? _controller.value * math.pi * 2 : 0.0;
        return SizedBox(
          width: 14,
          height: 10,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (var i = 0; i < 4; i++)
                Padding(
                  padding: EdgeInsets.only(right: i == 3 ? 0 : 2),
                  child: Container(
                    width: 2,
                    height: 3 + 5 * ((math.sin(phase + i * 1.4) + 1) / 2) + i,
                    decoration: BoxDecoration(
                      color: theme.primaryLight,
                      borderRadius: BorderRadius.circular(1),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _AlbumGrid extends StatelessWidget {
  const _AlbumGrid({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return GridView.builder(
      padding: const EdgeInsets.only(bottom: 8),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 142,
        mainAxisExtent: 182,
        crossAxisSpacing: 12,
        mainAxisSpacing: 10,
      ),
      itemCount: controller.albums.length,
      itemBuilder: (context, index) {
        final album = controller.albums[index];
        return MouseRegion(
          cursor: SystemMouseCursors.click,
          child: GestureDetector(
            onTap: () => controller.openAlbumEntry(album),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CoverArt(
                  url: controller.coverUrlFor(album.coverId, size: 256),
                  size: 124,
                  radius: 15,
                  glow: true,
                ),
                const SizedBox(height: 8),
                Text(
                  album.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: theme.text,
                    fontSize: 12.5,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  album.artist,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: theme.muted, fontSize: 10.5),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _ArtistList extends StatelessWidget {
  const _ArtistList({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: const EdgeInsets.only(bottom: 8),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 380,
        mainAxisExtent: 82,
        crossAxisSpacing: 10,
        mainAxisSpacing: 8,
      ),
      itemCount: controller.artists.length,
      itemBuilder: (context, index) {
        return _ArtistTile(
          controller: controller,
          artist: controller.artists[index],
          rank: index + 1,
        );
      },
    );
  }
}

class _ArtistTile extends StatefulWidget {
  const _ArtistTile({
    required this.controller,
    required this.artist,
    required this.rank,
  });

  final AppController controller;
  final Artist artist;
  final int rank;

  @override
  State<_ArtistTile> createState() => _ArtistTileState();
}

class _ArtistTileState extends State<_ArtistTile> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final artist = widget.artist;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: () => widget.controller.openArtistEntry(artist),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            color: _hover ? theme.track : Colors.transparent,
            border: Border.all(
              color: _hover ? theme.rimSoft : theme.separator,
            ),
          ),
          child: Row(
            children: [
              SizedBox(
                width: 30,
                child: Text(
                  widget.rank.toString().padLeft(2, '0'),
                  style: TextStyle(
                    color: widget.rank <= 3 ? theme.primaryText : theme.dim,
                    fontSize: 11,
                    fontWeight:
                        widget.rank <= 3 ? FontWeight.w700 : FontWeight.w500,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
              ),
              CoverArt(
                url: widget.controller.coverUrlFor(artist.coverId, size: 128),
                size: 46,
                radius: 23,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      artist.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: theme.text,
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${artist.songCount} 首歌曲'
                      '${artist.albumCount > 0 ? ' · ${artist.albumCount} 张专辑' : ''}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: theme.muted, fontSize: 10.5),
                    ),
                  ],
                ),
              ),
              Icon(LucideIcons.chevronRight, size: 14, color: theme.dim),
            ],
          ),
        ),
      ),
    );
  }
}

class _MiniLyrics extends StatelessWidget {
  const _MiniLyrics({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Container(
      height: 26,
      alignment: Alignment.center,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 280),
        child: Text(
          controller.miniLyric,
          key: ValueKey(controller.miniLyric),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
          style: TextStyle(color: theme.muted, fontSize: 11),
        ),
      ),
    );
  }
}

class _NoOverscrollBehavior extends ScrollBehavior {
  const _NoOverscrollBehavior();

  @override
  Widget buildOverscrollIndicator(
    BuildContext context,
    Widget child,
    ScrollableDetails details,
  ) =>
      child;
}
