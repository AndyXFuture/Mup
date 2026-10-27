import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../../core/app_controller.dart';
import '../../core/models.dart';
import '../components/controls.dart';
import '../components/cover_art.dart';
import '../components/glass_panel.dart';
import '../theme.dart';

class Sidebar extends StatefulWidget {
  const Sidebar({
    super.key,
    required this.controller,
    required this.searchController,
    required this.searchFocusNode,
    this.width = 200,
  });

  final AppController controller;
  final TextEditingController searchController;
  final FocusNode searchFocusNode;
  final double width;

  @override
  State<Sidebar> createState() => _SidebarState();
}

class _SidebarState extends State<Sidebar> {
  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final theme = MupTheme.of(context);
    return SizedBox(
      width: widget.width,
      child: GlassPanel(
        padding: const EdgeInsets.fromLTRB(10, 12, 10, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _SearchField(
              controller: widget.searchController,
              focusNode: widget.searchFocusNode,
              onSubmitted: controller.search,
              onClear: () {
                widget.searchController.clear();
                controller.selectNavigation('home');
              },
            ),
            const SizedBox(height: 8),
            _NavItem(
              icon: LucideIcons.home,
              label: '首页',
              active: controller.activeNav == 'home',
              onTap: () => controller.selectNavigation('home'),
            ),
            _NavItem(
              icon: LucideIcons.heart,
              label: '收藏',
              active: controller.activeNav == 'starred',
              onTap: () => controller.selectNavigation('starred'),
            ),
            _NavItem(
              icon: LucideIcons.clock,
              label: '最近播放',
              active: controller.activeNav == 'recent',
              onTap: () => controller.selectNavigation('recent'),
            ),
            _NavItem(
              icon: LucideIcons.user,
              label: '歌手',
              active: controller.activeNav == 'artists' ||
                  controller.activeNav.startsWith('artist:'),
              onTap: () => controller.selectNavigation('artists'),
            ),
            _NavItem(
              icon: LucideIcons.disc3,
              label: '专辑',
              active: controller.activeNav == 'albums' ||
                  controller.activeNav.startsWith('album:'),
              onTap: () => controller.selectNavigation('albums'),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 13, 6, 6),
              child: Row(
                children: [
                  Text(
                    '我的歌单',
                    style: TextStyle(
                      color: theme.primaryText,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.4,
                    ),
                  ),
                  const Spacer(),
                  MupIconButton(
                    icon: LucideIcons.rotateCw,
                    size: 22,
                    iconSize: 12,
                    tooltip: '刷新歌单',
                    onTap: controller.refreshPlaylists,
                  ),
                ],
              ),
            ),
            Expanded(
              child: ScrollConfiguration(
                behavior: const _NoScrollbarBehavior(),
                child: ListView.builder(
                  padding: EdgeInsets.zero,
                  itemCount: controller.playlists.length,
                  itemBuilder: (context, index) {
                    final playlist = controller.playlists[index];
                    return _PlaylistRow(
                      controller: controller,
                      playlist: playlist,
                      active: controller.activePlaylist?.id == playlist.id,
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SearchField extends StatefulWidget {
  const _SearchField({
    required this.controller,
    required this.focusNode,
    required this.onSubmitted,
    required this.onClear,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onSubmitted;
  final VoidCallback onClear;

  @override
  State<_SearchField> createState() => _SearchFieldState();
}

class _SearchFieldState extends State<_SearchField> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: MediaQuery.of(context).disableAnimations
            ? Duration.zero
            : const Duration(milliseconds: 180),
        height: 34,
        decoration: BoxDecoration(
          color: theme.track,
          borderRadius: BorderRadius.circular(11),
          border: Border.all(
            color: _hover ? theme.rimSoft : Colors.transparent,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: theme.dark ? 0.12 : 0.025),
              blurRadius: 5,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          children: [
            const SizedBox(width: 10),
            Icon(LucideIcons.search, size: 14, color: theme.dim),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: widget.controller,
                focusNode: widget.focusNode,
                maxLines: 1,
                textInputAction: TextInputAction.search,
                onSubmitted: widget.onSubmitted,
                style: TextStyle(color: theme.text, fontSize: 12),
                cursorColor: theme.primaryLight,
                decoration: InputDecoration(
                  isDense: true,
                  border: InputBorder.none,
                  hintText: '搜索歌曲、歌手',
                  hintStyle: TextStyle(color: theme.dim, fontSize: 12),
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            ),
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: widget.controller,
              builder: (context, value, _) => value.text.isEmpty
                  ? Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: Text(
                        'Ctrl F',
                        style: TextStyle(
                          color: theme.dim,
                          fontSize: 9,
                          letterSpacing: 0.2,
                        ),
                      ),
                    )
                  : MupIconButton(
                      icon: LucideIcons.x,
                      size: 26,
                      iconSize: 12,
                      onTap: widget.onClear,
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatefulWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.active,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  State<_NavItem> createState() => _NavItemState();
}

class _NavItemState extends State<_NavItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: MediaQuery.of(context).disableAnimations
              ? Duration.zero
              : const Duration(milliseconds: 180),
          height: 38,
          margin: const EdgeInsets.symmetric(vertical: 1),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          transform:
              Matrix4.translationValues(_hover && !widget.active ? 1 : 0, 0, 0),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(11),
            color: widget.active
                ? null
                : (_hover ? theme.track : Colors.transparent),
            gradient: widget.active
                ? LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      theme.primary.withValues(alpha: 0.22),
                      theme.primary.withValues(alpha: 0.09),
                    ],
                  )
                : null,
            border: widget.active
                ? Border.all(color: theme.primaryLight.withValues(alpha: 0.16))
                : null,
          ),
          child: Row(
            children: [
              Icon(
                widget.icon,
                size: 15,
                color: widget.active
                    ? theme.primaryText
                    : (_hover ? theme.text : theme.muted),
              ),
              const SizedBox(width: 10),
              Text(
                widget.label,
                style: TextStyle(
                  color: widget.active
                      ? theme.primaryText
                      : (_hover ? theme.text : theme.muted),
                  fontSize: 13,
                  fontWeight: widget.active ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PlaylistRow extends StatefulWidget {
  const _PlaylistRow({
    required this.controller,
    required this.playlist,
    required this.active,
  });

  final AppController controller;
  final Playlist playlist;
  final bool active;

  @override
  State<_PlaylistRow> createState() => _PlaylistRowState();
}

class _PlaylistRowState extends State<_PlaylistRow> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final cover = widget.controller.playlistCoverUrl(
      widget.playlist,
      size: 96,
    );
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => widget.controller.openPlaylist(widget.playlist),
        onDoubleTap: () async {
          await widget.controller.openPlaylist(widget.playlist);
          await widget.controller.playAll();
        },
        child: AnimatedContainer(
          duration: MediaQuery.of(context).disableAnimations
              ? Duration.zero
              : const Duration(milliseconds: 180),
          height: 40,
          margin: const EdgeInsets.symmetric(vertical: 1),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(11),
            color: widget.active
                ? null
                : (_hover ? theme.track : Colors.transparent),
            gradient: widget.active
                ? LinearGradient(
                    colors: [
                      theme.primary.withValues(alpha: 0.20),
                      theme.primary.withValues(alpha: 0.08),
                    ],
                  )
                : null,
          ),
          child: Row(
            children: [
              CoverArt(url: cover, size: 24, radius: 8),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  widget.playlist.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: widget.active
                        ? theme.primaryText
                        : (_hover ? theme.text : theme.muted),
                    fontSize: 12.5,
                    fontWeight:
                        widget.active ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
              if (widget.playlist.songCount > 0)
                Text(
                  '${widget.playlist.songCount}',
                  style: TextStyle(color: theme.dim, fontSize: 10.5),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NoScrollbarBehavior extends ScrollBehavior {
  const _NoScrollbarBehavior();

  @override
  Widget buildScrollbar(
          BuildContext context, Widget child, ScrollableDetails details) =>
      child;
}
