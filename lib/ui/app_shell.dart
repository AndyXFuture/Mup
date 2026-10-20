import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:window_manager/window_manager.dart';

import '../core/app_controller.dart';
import 'pages/connect_page.dart';
import 'pages/library_page.dart';
import 'pages/player_page.dart';
import 'pages/settings_page.dart';
import 'theme.dart';

class MupAppShell extends StatelessWidget {
  const MupAppShell({super.key, required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final dark = switch (controller.config.themeMode) {
      'dark' => true,
      'light' => false,
      _ => PlatformDispatcher.instance.platformBrightness == Brightness.dark,
    };
    return Theme(
      data: MupTheme.material(dark),
      child: Builder(
        builder: (context) {
          final theme = MupTheme.of(context);
          return ColoredBox(
            color: theme.backgroundBottom,
            child: Stack(
              fit: StackFit.expand,
              children: [
                DecoratedBox(
                    decoration:
                        BoxDecoration(gradient: theme.backgroundGradient)),
                Positioned(
                  left: -170,
                  top: -180,
                  width: 620,
                  height: 500,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: RadialGradient(
                        colors: [theme.ambient, Colors.transparent],
                      ),
                    ),
                  ),
                ),
                _AnimatedWindow(
                  controller: controller,
                  child: Column(
                    children: [
                      MupTitleBar(controller: controller),
                      Expanded(child: _body(controller)),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _body(AppController controller) {
    if (controller.stage == AppStage.checking) {
      return const _ConnectionSplash();
    }
    if (controller.stage == AppStage.connect) {
      return ConnectPage(controller: controller);
    }
    return AnimatedSwitcher(
      duration: controller.config.reduceMotion
          ? Duration.zero
          : const Duration(milliseconds: 260),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      child: switch (controller.page) {
        AppPage.player => PlayerPage(
            key: const ValueKey('player'),
            controller: controller,
          ),
        AppPage.settings => SettingsPage(
            key: const ValueKey('settings'),
            controller: controller,
          ),
        AppPage.library => LibraryPage(
            key: const ValueKey('library'),
            controller: controller,
          ),
      },
    );
  }
}

class _AnimatedWindow extends StatelessWidget {
  const _AnimatedWindow({required this.controller, required this.child});

  final AppController controller;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!controller.config.reduceMotion) return child;
    return MediaQuery(
      data: MediaQuery.of(context).copyWith(disableAnimations: true),
      child: child,
    );
  }
}

class MupTitleBar extends StatefulWidget {
  const MupTitleBar({super.key, required this.controller});

  final AppController controller;

  @override
  State<MupTitleBar> createState() => _MupTitleBarState();
}

class _MupTitleBarState extends State<MupTitleBar> {
  bool _maximized = false;

  @override
  void initState() {
    super.initState();
    _refreshMaximized();
  }

  Future<void> _refreshMaximized() async {
    final value = await windowManager.isMaximized();
    if (mounted) setState(() => _maximized = value);
  }

  Future<void> _toggleMaximize() async {
    if (await windowManager.isMaximized()) {
      await windowManager.unmaximize();
    } else {
      await windowManager.maximize();
    }
    await _refreshMaximized();
  }

  Future<void> _startDrag() async {
    if (await windowManager.isMaximized()) {
      await windowManager.unmaximize();
      await Future<void>.delayed(const Duration(milliseconds: 45));
    }
    await windowManager.startDragging();
  }

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return SizedBox(
      height: 44,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Row(
          children: [
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onPanStart: (_) => _startDrag(),
              onDoubleTap: _toggleMaximize,
              child: Row(
                children: [
                  SizedBox(
                    width: 20,
                    height: 20,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: Image.asset(
                        'assets/app_icon.png',
                        width: 20,
                        height: 20,
                        fit: BoxFit.cover,
                        filterQuality: FilterQuality.high,
                      ),
                    ),
                  ),
                  const SizedBox(width: 9),
                  Text(
                    '音珏 - Mup',
                    style: TextStyle(
                      color: theme.text,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.3,
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onPanStart: (_) => _startDrag(),
                onDoubleTap: _toggleMaximize,
                child: const SizedBox.expand(),
              ),
            ),
            _WindowIcon(
              icon: LucideIcons.settings,
              onTap: widget.controller.page == AppPage.settings
                  ? widget.controller.openLibrary
                  : widget.controller.openSettings,
            ),
            const SizedBox(width: 12),
            _WindowIcon(
              icon: LucideIcons.minus,
              onTap: windowManager.minimize,
            ),
            const SizedBox(width: 12),
            _WindowIcon(
              icon: _maximized ? LucideIcons.copy : LucideIcons.square,
              onTap: _toggleMaximize,
            ),
            const SizedBox(width: 12),
            _WindowIcon(
              icon: LucideIcons.x,
              onTap: windowManager.close,
            ),
          ],
        ),
      ),
    );
  }
}

class _WindowIcon extends StatefulWidget {
  const _WindowIcon({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  State<_WindowIcon> createState() => _WindowIconState();
}

class _WindowIconState extends State<_WindowIcon> {
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
        child: SizedBox(
          width: 18,
          height: 26,
          child: Icon(
            widget.icon,
            size: 14,
            color: _hover ? theme.text : theme.dim,
          ),
        ),
      ),
    );
  }
}

class _ConnectionSplash extends StatelessWidget {
  const _ConnectionSplash();

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 50,
            height: 50,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(17),
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF7A76FF), Color(0xFF5651D8)],
              ),
              boxShadow: [
                BoxShadow(
                  color: theme.primary.withValues(alpha: 0.48),
                  blurRadius: 28,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child:
                const Icon(LucideIcons.music3, color: Colors.white, size: 24),
          ),
          const SizedBox(height: 18),
          Text(
            '正在恢复音乐现场',
            style: TextStyle(color: theme.muted, fontSize: 12),
          ),
        ],
      ),
    );
  }
}
