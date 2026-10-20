import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';

import 'core/app_config.dart';
import 'core/app_controller.dart';
import 'core/windows_integration.dart';
import 'ui/app_shell.dart';
import 'ui/theme.dart';

Future<void> main(List<String> arguments) async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();

  final controller = AppController();
  final demoMode = arguments.contains('--demo');
  if (demoMode) {
    controller.prepareDemo(
      themeMode: arguments.contains('--light') ? 'light' : 'dark',
    );
  } else {
    await controller.initialize();
    if (arguments.contains('--light')) controller.setThemeMode('light');
    if (arguments.contains('--dark')) controller.setThemeMode('dark');
  }
  if (arguments.contains('--settings')) controller.openSettings();
  if (arguments.contains('--player')) controller.openPlayer();
  if (arguments.contains('--connect-preview')) controller.openConnect();
  if (arguments.contains('--artists')) {
    await controller.selectNavigation('artists');
  }
  if (arguments.contains('--artist-detail')) {
    await controller.selectNavigation('artists');
    final artist = controller.artists.where((item) => item.name == '薛之谦');
    if (artist.isNotEmpty) await controller.openArtistEntry(artist.first);
  }
  final snapshot = controller.config.window;
  final size = Size(
    snapshot.width.clamp(980, 2400),
    snapshot.height.clamp(622, 1600),
  );
  final options = WindowOptions(
    size: size,
    center: snapshot.x == 0 && snapshot.y == 0,
    minimumSize: const Size(980, 622),
    backgroundColor: Colors.transparent,
    skipTaskbar: false,
    title: '音珏 - Mup',
    titleBarStyle: TitleBarStyle.hidden,
  );
  await windowManager.waitUntilReadyToShow(options, () async {});

  final backgroundLaunch = arguments.contains('--background');
  runApp(MupRoot(
    controller: controller,
    backgroundLaunch: backgroundLaunch,
    desktopIntegration: !arguments.contains('--no-desktop'),
  ));

  WidgetsBinding.instance.addPostFrameCallback((_) async {
    if (snapshot.x != 0 || snapshot.y != 0) {
      await windowManager.setBounds(
        Rect.fromLTWH(
          snapshot.x,
          snapshot.y,
          snapshot.width.clamp(980, 2400),
          snapshot.height.clamp(622, 1600),
        ),
      );
    }
    if (snapshot.maximized) await windowManager.maximize();
    if (backgroundLaunch) {
      await windowManager.hide();
    } else {
      await windowManager.show();
      await windowManager.focus();
    }
  });
}

class MupRoot extends StatefulWidget {
  const MupRoot({
    super.key,
    required this.controller,
    required this.backgroundLaunch,
    required this.desktopIntegration,
  });

  final AppController controller;
  final bool backgroundLaunch;
  final bool desktopIntegration;

  @override
  State<MupRoot> createState() => _MupRootState();
}

class _MupRootState extends State<MupRoot>
    with WidgetsBindingObserver, WindowListener, TrayListener {
  late final MediaKeyService _mediaKeys =
      MediaKeyService(widget.controller.audio);
  bool _quitting = false;
  bool _trayReady = false;

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
    trayManager.addListener(this);
    WidgetsBinding.instance.addObserver(this);
    widget.controller.addListener(_rebuild);
    WidgetsBinding.instance.addPostFrameCallback((_) => _initializeDesktop());
  }

  void _rebuild() {
    if (mounted) setState(() {});
  }

  Future<void> _initializeDesktop() async {
    if (!widget.desktopIntegration) return;
    debugPrint('desktop: setPreventClose');
    await windowManager.setPreventClose(true);
    debugPrint('desktop: register media keys');
    await _mediaKeys.register();
    debugPrint('desktop: media keys ready');
    try {
      debugPrint('desktop: set tray icon');
      await trayManager.setIcon('assets/app_icon.ico');
      debugPrint('desktop: set tray tooltip');
      await trayManager.setToolTip('音珏 - Mup');
      debugPrint('desktop: set tray menu');
      await trayManager.setContextMenu(Menu(items: [
        MenuItem(key: 'show', label: '显示主界面'),
        MenuItem.separator(),
        MenuItem(key: 'exit', label: '退出'),
      ]));
      _trayReady = true;
      debugPrint('desktop: tray ready');
    } catch (error) {
      debugPrint('托盘初始化失败: $error');
    }
  }

  Future<void> _saveWindow() async {
    if (await windowManager.isMaximized()) {
      final previous = widget.controller.config.window;
      widget.controller.updateWindowSnapshot(WindowSnapshot(
        x: previous.x,
        y: previous.y,
        width: previous.width,
        height: previous.height,
        maximized: true,
      ));
      return;
    }
    final bounds = await windowManager.getBounds();
    widget.controller.updateWindowSnapshot(WindowSnapshot(
      x: bounds.left,
      y: bounds.top,
      width: bounds.width,
      height: bounds.height,
    ));
  }

  Future<void> _showWindow() async {
    await windowManager.show();
    await windowManager.focus();
  }

  Future<void> _quit() async {
    if (_quitting) return;
    _quitting = true;
    await _saveWindow();
    await _mediaKeys.unregister();
    await widget.controller.shutdown();
    if (_trayReady) await trayManager.destroy();
    await windowManager.setPreventClose(false);
    await windowManager.destroy();
  }

  @override
  void onWindowClose() async {
    if (_quitting) return;
    if (!_trayReady) {
      await _quit();
      return;
    }
    await _saveWindow();
    await windowManager.hide();
  }

  @override
  void onTrayIconMouseDown() {
    _showWindow();
  }

  @override
  void onTrayIconRightMouseDown() {
    trayManager.popUpContextMenu();
  }

  @override
  void onTrayMenuItemClick(MenuItem menuItem) {
    if (menuItem.key == 'show') {
      _showWindow();
    } else if (menuItem.key == 'exit') {
      _quit();
    }
  }

  @override
  void didChangePlatformBrightness() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    trayManager.removeListener(this);
    WidgetsBinding.instance.removeObserver(this);
    widget.controller.removeListener(_rebuild);
    widget.controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dark = switch (widget.controller.config.themeMode) {
      'dark' => true,
      'light' => false,
      _ => PlatformDispatcher.instance.platformBrightness == Brightness.dark,
    };
    return MaterialApp(
      title: '音珏 - Mup',
      debugShowCheckedModeBanner: false,
      scrollBehavior:
          const MaterialScrollBehavior().copyWith(scrollbars: false),
      theme: MupTheme.material(dark),
      home: Material(
        color: Colors.transparent,
        child: Shortcuts(
          shortcuts: const {
            SingleActivator(LogicalKeyboardKey.escape): _BackIntent(),
          },
          child: Actions(
            actions: {
              _BackIntent: CallbackAction<_BackIntent>(
                onInvoke: (_) {
                  if (widget.controller.page != AppPage.library) {
                    widget.controller.openLibrary();
                    return true;
                  }
                  return null;
                },
              ),
            },
            child: Focus(
              autofocus: true,
              child: MupAppShell(controller: widget.controller),
            ),
          ),
        ),
      ),
    );
  }
}

class _BackIntent extends Intent {
  const _BackIntent();
}
