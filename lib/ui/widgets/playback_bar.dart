import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../../core/app_controller.dart';
import '../../core/audio_controller.dart';
import '../../core/models.dart';
import '../components/controls.dart';
import '../components/cover_art.dart';
import '../components/glass_panel.dart';
import '../theme.dart';

class PlaybackBar extends StatelessWidget {
  const PlaybackBar({
    super.key,
    required this.controller,
    this.immersive = false,
    this.horizontalPadding = 20,
  });

  final AppController controller;
  final bool immersive;
  final double horizontalPadding;

  @override
  Widget build(BuildContext context) {
    final audio = controller.audio;
    final song = audio.currentSong;
    return SizedBox(
      height: 104,
      child: Stack(
        fit: StackFit.expand,
        clipBehavior: Clip.none,
        children: [
          GlassPanel(
            radius: 18,
            blur: 22,
            padding: EdgeInsets.fromLTRB(
              horizontalPadding,
              11,
              horizontalPadding,
              12,
            ),
            child: Stack(
              fit: StackFit.expand,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Expanded(
                      child: _LeftTrack(
                        controller: controller,
                        song: song,
                        immersive: immersive,
                      ),
                    ),
                    const SizedBox(width: 390),
                    Expanded(
                      child: _RightControls(controller: controller),
                    ),
                  ],
                ),
                Align(
                  alignment: Alignment.center,
                  child: SizedBox(
                    width: 380,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _TransportControls(controller: controller),
                        const SizedBox(height: 7),
                        _ProgressStrip(controller: controller),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          const Positioned(
            top: -24,
            left: 0,
            right: 0,
            child: Align(
              alignment: Alignment.topCenter,
              child: IgnorePointer(child: GlowDivider(width: 600)),
            ),
          ),
        ],
      ),
    );
  }
}

class _LeftTrack extends StatelessWidget {
  const _LeftTrack({
    required this.controller,
    required this.song,
    required this.immersive,
  });

  final AppController controller;
  final Song? song;
  final bool immersive;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Row(
      children: [
        if (!immersive)
          GestureDetector(
            onTap: controller.openPlayer,
            child: MouseRegion(
              cursor: SystemMouseCursors.click,
              child: CoverArt(
                key: ValueKey('${song?.id}:${song?.coverId}'),
                url: song == null ? '' : controller.coverUrlFor(song!.coverId),
                size: 56,
                radius: 13,
                glow: true,
              ),
            ),
          ),
        if (!immersive) const SizedBox(width: 12),
        Flexible(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(LucideIcons.heart, size: 14, color: theme.danger),
                  const SizedBox(width: 7),
                  Flexible(
                    child: Text(
                      song?.title ?? '未在播放',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: theme.text,
                        fontSize: 13.5,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _TextLink(
                    text:
                        song?.artist.isNotEmpty == true ? song!.artist : '未知歌手',
                    onTap: song == null
                        ? null
                        : () => controller.openArtist(song!),
                    theme: theme,
                  ),
                  if (song?.album.isNotEmpty == true)
                    Text(
                      ' · ',
                      style: TextStyle(color: theme.muted, fontSize: 11),
                    ),
                  if (song?.album.isNotEmpty == true)
                    Flexible(
                      child: _TextLink(
                        text: song!.album,
                        onTap: () => controller.openAlbum(song!),
                        theme: theme,
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _TextLink extends StatefulWidget {
  const _TextLink({
    required this.text,
    required this.onTap,
    required this.theme,
  });

  final String text;
  final VoidCallback? onTap;
  final MupTheme theme;

  @override
  State<_TextLink> createState() => _TextLinkState();
}

class _TextLinkState extends State<_TextLink> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
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
            color: _hover ? widget.theme.primaryText : widget.theme.muted,
            fontSize: 11,
            decoration: _hover ? TextDecoration.underline : TextDecoration.none,
            decorationColor: widget.theme.primaryLight,
          ),
        ),
      ),
    );
  }
}

class _TransportControls extends StatelessWidget {
  const _TransportControls({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final audio = controller.audio;
    final playing = audio.state == MupPlaybackState.playing;
    return SizedBox(
      height: 44,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          MupIconButton(
            icon: LucideIcons.skipBack,
            iconSize: 17,
            size: 30,
            onTap: audio.previous,
          ),
          const SizedBox(width: 12),
          _PlayButton(
            playing: playing,
            busy: audio.buffering,
            onTap: audio.toggle,
          ),
          const SizedBox(width: 12),
          MupIconButton(
            icon: LucideIcons.skipForward,
            iconSize: 17,
            size: 30,
            onTap: audio.next,
          ),
          if (audio.error != null)
            Padding(
              padding: const EdgeInsets.only(left: 5),
              child: Tooltip(
                message: audio.error!,
                child: Icon(LucideIcons.alertCircle,
                    size: 14, color: theme.danger),
              ),
            ),
        ],
      ),
    );
  }
}

class _PlayButton extends StatefulWidget {
  const _PlayButton({
    required this.playing,
    required this.busy,
    required this.onTap,
  });

  final bool playing;
  final bool busy;
  final VoidCallback onTap;

  @override
  State<_PlayButton> createState() => _PlayButtonState();
}

class _PlayButtonState extends State<_PlayButton> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFF7A76FF), Color(0xFF5752D9)],
            ),
            border: Border.all(color: Colors.white.withValues(alpha: 0.26)),
            boxShadow: [
              BoxShadow(
                color: theme.primary.withValues(alpha: _hover ? 0.68 : 0.52),
                blurRadius: _hover ? 26 : 20,
                spreadRadius: -4,
                offset: const Offset(0, 8),
              ),
              BoxShadow(
                color: theme.primary.withValues(alpha: 0.16),
                blurRadius: _hover ? 16 : 10,
                spreadRadius: _hover ? 7 : 5,
              ),
            ],
          ),
          child: widget.busy
              ? const Padding(
                  padding: EdgeInsets.all(14),
                  child: CircularProgressIndicator(
                    strokeWidth: 1.8,
                    color: Colors.white,
                  ),
                )
              : Icon(
                  widget.playing ? LucideIcons.pause : LucideIcons.play,
                  size: 18,
                  color: Colors.white,
                  fill: widget.playing ? 0 : 1,
                ),
        ),
      ),
    );
  }
}

class _ProgressStrip extends StatefulWidget {
  const _ProgressStrip({required this.controller});

  final AppController controller;

  @override
  State<_ProgressStrip> createState() => _ProgressStripState();
}

class _ProgressStripState extends State<_ProgressStrip> {
  double? _hoverMs;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final audio = widget.controller.audio;
    final duration = audio.duration.inMilliseconds > 0
        ? audio.duration
        : Duration(seconds: audio.currentSong?.duration ?? 0);
    final maxMs = math.max(1, duration.inMilliseconds);
    final value = audio.position.inMilliseconds.clamp(0, maxMs).toDouble();
    final displayPosition = _hoverMs == null
        ? audio.position
        : Duration(milliseconds: _hoverMs!.round());
    final timeStyle = TextStyle(
      color: theme.muted,
      fontSize: 10.5,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
    return SizedBox(
      height: 16,
      child: Row(
        children: [
          SizedBox(
            width: 42,
            child: Text(
              _time(displayPosition),
              textAlign: TextAlign.right,
              style: timeStyle,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: HoverProgressBar(
              value: value,
              max: maxMs.toDouble(),
              onChanged: (next) =>
                  audio.seek(Duration(milliseconds: next.round())),
              height: 16,
              trackHeight: 2,
              showThumbOnHover: true,
              onHover: (position) => setState(() => _hoverMs = position),
              onHoverExit: () => setState(() => _hoverMs = null),
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 42,
            child: Text(
              _time(duration),
              textAlign: TextAlign.left,
              style: timeStyle,
            ),
          ),
        ],
      ),
    );
  }

  static String _time(Duration value) {
    final total = math.max(0, value.inSeconds);
    final minutes = total ~/ 60;
    final seconds = total % 60;
    return '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}';
  }
}

class _RightControls extends StatelessWidget {
  const _RightControls({required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final audio = controller.audio;
    final modeIcon = switch (audio.mode) {
      'random' => LucideIcons.shuffle,
      'single' => LucideIcons.repeat1,
      'order' => LucideIcons.listOrdered,
      _ => LucideIcons.repeat,
    };
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        MupIconButton(
          icon: modeIcon,
          iconSize: 16,
          size: 30,
          tooltip: _modeLabel(audio.mode),
          onTap: () {
            const modes = ['list', 'random', 'single', 'order'];
            final next = (modes.indexOf(audio.mode) + 1) % modes.length;
            audio.setMode(modes[next]);
          },
        ),
        const SizedBox(width: 5),
        MupIconButton(
          icon: LucideIcons.messageSquare,
          iconSize: 16,
          size: 30,
          tooltip: '歌词',
          onTap: controller.openPlayer,
        ),
        const SizedBox(width: 11),
        MupIconButton(
          icon: audio.volume == 0
              ? LucideIcons.volumeX
              : audio.volume < 50
                  ? LucideIcons.volume1
                  : LucideIcons.volume2,
          size: 28,
          iconSize: 16,
          tooltip: audio.volume == 0 ? '取消静音' : '静音',
          onTap: audio.toggleMute,
        ),
        const SizedBox(width: 6),
        SizedBox(
          width: 104,
          child: HoverProgressBar(
            value: audio.volume.toDouble(),
            max: 100,
            onChanged: (value) => audio.setVolume(value.round()),
            height: 24,
            trackHeight: 4,
            accent: true,
            showThumbOnHover: true,
            onHover: (_) {},
            onHoverExit: () {},
          ),
        ),
      ],
    );
  }

  String _modeLabel(String mode) => switch (mode) {
        'random' => '随机播放',
        'single' => '单曲循环',
        'order' => '顺序播放',
        _ => '列表循环',
      };
}

class HoverProgressBar extends StatefulWidget {
  const HoverProgressBar({
    super.key,
    required this.value,
    required this.max,
    required this.onChanged,
    this.height = 16,
    this.trackHeight = 2,
    this.accent = false,
    this.showThumbOnHover = false,
    this.onHover,
    this.onHoverExit,
  });

  final double value;
  final double max;
  final ValueChanged<double> onChanged;
  final double height;
  final double trackHeight;
  final bool accent;
  final bool showThumbOnHover;
  final ValueChanged<double>? onHover;
  final VoidCallback? onHoverExit;

  @override
  State<HoverProgressBar> createState() => _HoverProgressBarState();
}

class _HoverProgressBarState extends State<HoverProgressBar> {
  bool _hover = false;
  bool _dragging = false;
  double? _hoverFraction;

  double _position(Offset local, double width) =>
      (local.dx / width).clamp(0, 1) * widget.max;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final fraction =
            widget.max <= 0 ? 0.0 : (widget.value / widget.max).clamp(0.0, 1.0);
        final thumbFraction = (_hover || _dragging) && _hoverFraction != null
            ? _hoverFraction!
            : fraction;
        return MouseRegion(
          cursor: SystemMouseCursors.click,
          onEnter: (_) => setState(() => _hover = true),
          onExit: (_) {
            setState(() => _hover = false);
            widget.onHoverExit?.call();
          },
          child: Listener(
            behavior: HitTestBehavior.opaque,
            onPointerHover: (event) {
              final value = _position(event.localPosition, width);
              setState(() => _hoverFraction = value / widget.max);
              widget.onHover?.call(value);
            },
            onPointerDown: (event) {
              final value = _position(event.localPosition, width);
              setState(() {
                _dragging = true;
                _hoverFraction = value / widget.max;
              });
              widget.onChanged(value);
            },
            onPointerMove: (event) {
              if ((event.buttons & kPrimaryMouseButton) == 0) return;
              final value = _position(event.localPosition, width);
              setState(() => _hoverFraction = value / widget.max);
              widget.onChanged(value);
            },
            onPointerUp: (_) => setState(() => _dragging = false),
            onPointerCancel: (_) => setState(() => _dragging = false),
            child: SizedBox(
              width: double.infinity,
              height: widget.height,
              child: Center(
                child: SizedBox(
                  width: double.infinity,
                  height: widget.trackHeight,
                  child: Stack(
                    fit: StackFit.expand,
                    clipBehavior: Clip.none,
                    alignment: Alignment.centerLeft,
                    children: [
                      Positioned.fill(
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            color: widget.accent
                                ? (theme.dark
                                    ? Colors.white.withValues(alpha: 0.12)
                                    : const Color(0x221A1B22))
                                : (theme.dark
                                    ? Colors.white.withValues(alpha: 0.24)
                                    : const Color(0x2E1A1B22)),
                            borderRadius:
                                BorderRadius.circular(widget.trackHeight / 2),
                          ),
                        ),
                      ),
                      FractionallySizedBox(
                        widthFactor: fraction,
                        heightFactor: 1,
                        alignment: Alignment.centerLeft,
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            borderRadius:
                                BorderRadius.circular(widget.trackHeight / 2),
                            gradient: widget.accent
                                ? LinearGradient(
                                    colors: [theme.primary, theme.primaryLight],
                                  )
                                : null,
                            color: widget.accent
                                ? null
                                : (theme.dark
                                    ? const Color(0xFFF4F5FA)
                                    : const Color(0xD91A1B22)),
                            boxShadow: widget.accent
                                ? [
                                    BoxShadow(
                                      color:
                                          theme.primary.withValues(alpha: 0.78),
                                      blurRadius: 8,
                                    ),
                                    BoxShadow(
                                      color: theme.primaryLight
                                          .withValues(alpha: 0.28),
                                      blurRadius: 18,
                                      spreadRadius: 2,
                                    ),
                                  ]
                                : null,
                          ),
                        ),
                      ),
                      Positioned(
                        left: math.max(0, width * thumbFraction - 4),
                        child: AnimatedOpacity(
                          opacity:
                              (!widget.showThumbOnHover || _hover || _dragging)
                                  ? 1
                                  : 0,
                          duration: const Duration(milliseconds: 140),
                          child: Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: widget.accent
                                  ? Colors.white
                                  : (theme.dark
                                      ? Colors.white
                                      : const Color(0xFF2A2B33)),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.white.withValues(
                                      alpha: theme.dark ? 0.55 : 0.9),
                                  blurRadius: 5,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
