import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../../core/app_controller.dart';
import '../../core/models.dart';
import '../components/controls.dart';
import '../components/cover_art.dart';
import '../theme.dart';
import '../widgets/playback_bar.dart';

class PlayerPage extends StatelessWidget {
  const PlayerPage({super.key, required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Column(
      children: [
        SizedBox(
          height: 44,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            child: Row(
              children: [
                MupIconButton(
                  icon: LucideIcons.arrowLeft,
                  size: 34,
                  iconSize: 16,
                  onTap: controller.openLibrary,
                ),
                const SizedBox(width: 12),
                Text(
                  '正在播放',
                  style: TextStyle(
                    color: theme.muted,
                    fontSize: 13,
                    letterSpacing: 0.3,
                  ),
                ),
                const Spacer(),
                Icon(LucideIcons.heart, size: 16, color: theme.danger),
                const SizedBox(width: 18),
                MupIconButton(
                  icon: LucideIcons.moreHorizontal,
                  size: 28,
                  iconSize: 17,
                  onTap: () {},
                ),
              ],
            ),
          ),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(28, 8, 28, 16),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final coverSize = math
                    .min(
                      math.min(constraints.maxHeight - 48,
                          constraints.maxWidth * 0.38),
                      300,
                    )
                    .toDouble();
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(
                      child: Center(
                        child: AnimatedSwitcher(
                          duration: controller.config.reduceMotion
                              ? Duration.zero
                              : const Duration(milliseconds: 520),
                          switchInCurve: Curves.easeOutCubic,
                          transitionBuilder: (child, animation) =>
                              FadeTransition(
                            opacity: animation,
                            child: ScaleTransition(
                              scale: Tween(begin: 0.965, end: 1.0)
                                  .animate(animation),
                              child: child,
                            ),
                          ),
                          child: CoverArt(
                            key: ValueKey(controller.audio.currentSong?.id),
                            url: controller.coverUrlFor(
                              controller.audio.currentSong?.coverId ?? '',
                              size: 700,
                            ),
                            size: coverSize,
                            radius: 28,
                            glow: true,
                          ),
                        ),
                      ),
                    ),
                    Expanded(
                      child: Container(
                        decoration: BoxDecoration(
                          border: Border(
                            left: BorderSide(color: theme.separator, width: 1),
                          ),
                        ),
                        padding: const EdgeInsets.only(left: 48),
                        child: _LyricsPane(controller: controller),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: PlaybackBar(
            controller: controller,
            immersive: true,
            horizontalPadding: 24,
          ),
        ),
      ],
    );
  }
}

class _LyricsPane extends StatefulWidget {
  const _LyricsPane({required this.controller});

  final AppController controller;

  @override
  State<_LyricsPane> createState() => _LyricsPaneState();
}

class _LyricsPaneState extends State<_LyricsPane> {
  late final ScrollController _scroll;
  int _lastIndex = -1;

  @override
  void didUpdateWidget(covariant _LyricsPane oldWidget) {
    super.didUpdateWidget(oldWidget);
    _scheduleScroll();
  }

  @override
  void initState() {
    super.initState();
    final initial = widget.controller.lyrics.isEmpty
        ? 3
        : widget.controller.activeLyricIndex
            .clamp(0, widget.controller.lyrics.length - 1);
    _scroll = ScrollController(initialScrollOffset: initial * 36.0);
    WidgetsBinding.instance.addPostFrameCallback((_) => _scheduleScroll());
  }

  void _scheduleScroll() {
    final index = widget.controller.activeLyricIndex;
    if (index == _lastIndex || !_scroll.hasClients) return;
    _lastIndex = index;
    final target =
        (index.clamp(0, math.max(0, widget.controller.lyrics.length - 1)) *
                36.0)
            .clamp(0.0, _scroll.position.maxScrollExtent);
    _scroll.animateTo(
      target,
      duration: widget.controller.config.reduceMotion
          ? Duration.zero
          : const Duration(milliseconds: 420),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final controller = widget.controller;
    final lines = controller.lyrics.isEmpty
        ? _fallbackLyrics(controller.audio.currentSong)
        : controller.lyrics;
    final active = controller.lyrics.isEmpty
        ? 3
        : controller.activeLyricIndex.clamp(0, lines.length - 1);
    return LayoutBuilder(
      builder: (context, constraints) {
        return ListView.builder(
          controller: _scroll,
          physics: const ClampingScrollPhysics(),
          padding: EdgeInsets.symmetric(
              vertical: math.max(12, constraints.maxHeight / 2 - 20)),
          itemCount: lines.length,
          itemBuilder: (context, index) {
            final distance = (index - active).abs();
            final isActive = index == active;
            final opacity = isActive
                ? 1.0
                : math.max(theme.dark ? 0.28 : 0.38, 0.72 - distance * 0.12);
            return SizedBox(
              height: 36,
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  lines[index].text,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: isActive
                        ? theme.text
                        : theme.muted.withValues(alpha: opacity),
                    fontSize: isActive ? 18 : 14.5,
                    height: 1.45,
                    fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  List<LyricLine> _fallbackLyrics(Song? song) {
    final title = song?.title ?? '音乐与此刻';
    final artist = song?.artist ?? '';
    return [
      const LyricLine(0, '房间里，光慢下来'),
      const LyricLine(0, '让旋律替时间说话'),
      const LyricLine(0, '每一段安静都有回声'),
      LyricLine(0, '正在播放 · $title'),
      if (artist.isNotEmpty) LyricLine(0, artist),
      const LyricLine(0, '把耳机里的世界，留给此刻'),
      const LyricLine(0, '音珏 · Mup'),
    ];
  }
}
