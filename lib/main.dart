import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:screen_retriever/screen_retriever.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';

import 'core/app_config.dart';
import 'core/app_controller.dart';
import 'core/window_bounds.dart';
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
  final hasSavedPosition = snapshot.hasPosition;
  final size = Size(
    snapshot.width.clamp(980, 2400),
    snapshot.height.clamp(622, 1600),
  );
  final options = WindowOptions(
    size: size,
    center: !hasSavedPosition,
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
    if (hasSavedPosition) {
      final requested = Rect.fromLTWH(
        snapshot.x,
        snapshot.y,
        snapshot.width.clamp(980, 2400),
        snapshot.height.clamp(622, 1600),
      );
      await windowManager.setBounds(await _repairBounds(requested));
    }
    if (snapshot.maximized) await windowManager.maximize();
    if (backgroundLaunch) {
      await windowManager.hide();
    } else {
      await windowManager.show();
      await windowManager.focus();
    }
    try {
      await MediaKeyService(controller.audio).markReady();
    } catch (_) {}
  });
}

Future<Rect> _repairBounds(Rect desired) async {
  try {
    final displays = await screenRetriever.getAllDisplays();
    final primary = await screenRetriever.getPrimaryDisplay();
    final primaryArea = (primary.visiblePosition ?? Offset.zero) &
        (primary.visibleSize ?? primary.size);
    final areas = <Rect>[primaryArea];
    for (final display in displays) {
      final origin = display.visiblePosition ?? Offset.zero;
      final areaSize = display.visibleSize ?? display.size;
      final area = origin & areaSize;
      if (area != primaryArea) areas.add(area);
    }
    return repairWindowBounds(desired, areas);
  } catch (error) {
    debugPrint('无法读取显示器布局，使用安全默认位置: $error');
    return Rect.fromLTWH(40, 40, desired.width, desired.height);
  }
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
  final GlobalKey<ScaffoldMessengerState> _scaffoldMessengerKey =
      GlobalKey<ScaffoldMessengerState>();
  bool _quitting = false;
  bool _trayReady = false;
  Future<void>? _desktopInitialization;
  Rect? _lastNormalBounds;

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
    trayManager.addListener(this);
    WidgetsBinding.instance.addObserver(this);
    widget.controller.addListener(_rebuild);
    widget.controller.actionError.addListener(_showActionError);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _quitting) return;
      _desktopInitialization = _initializeDesktop();
    });
  }

  void _rebuild() {
    if (mounted) setState(() {});
  }

  void _showActionError() {
    final message = widget.controller.actionError.value;
    if (message == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      widget.controller.clearActionError();
      _scaffoldMessengerKey.currentState?.showSnackBar(
        SnackBar(
          content: Text(message),
          behavior: SnackBarBehavior.floating,
        ),
        snackBarAnimationStyle: widget.controller.config.reduceMotion
            ? AnimationStyle.noAnimation
            : null,
      );
    });
  }

  Future<void> _initializeDesktop() async {
    if (!widget.desktopIntegration || !mounted || _quitting) return;
    try {
      debugPrint('desktop: setPreventClose');
      await windowManager.setPreventClose(true);
    } catch (error) {
      debugPrint('窗口关闭拦截初始化失败: $error');
    }
    if (!mounted || _quitting) return;
    try {
      debugPrint('desktop: register media keys');
      await _mediaKeys.register();
      debugPrint('desktop: media keys ready');
    } catch (error) {
      debugPrint('媒体键初始化失败: $error');
    }
    if (!mounted || _quitting) return;
    try {
      debugPrint('desktop: set tray icon');
      await trayManager.setIcon('assets/app_icon.ico');
      if (!mounted || _quitting) return;
      debugPrint('desktop: set tray tooltip');
      await trayManager.setToolTip('音珏 - Mup');
      if (!mounted || _quitting) return;
      debugPrint('desktop: set tray menu');
      await trayManager.setContextMenu(Menu(items: [
        MenuItem(key: 'show', label: '显示主界面'),
        MenuItem.separator(),
        MenuItem(key: 'exit', label: '退出'),
      ]));
      _trayReady = true;
      if (!mounted || _quitting) return;
      debugPrint('desktop: tray ready');
    } catch (error) {
      debugPrint('托盘初始化失败: $error');
    }
  }

  Future<void> _saveWindow() async {
    if (await windowManager.isMaximized()) {
      final previous = widget.controller.config.window;
      final normal = _lastNormalBounds ??
          Rect.fromLTWH(
            previous.x,
            previous.y,
            previous.width,
            previous.height,
          );
      final repaired = await _repairBounds(normal);
      widget.controller.updateWindowSnapshot(WindowSnapshot(
        x: repaired.left,
        y: repaired.top,
        width: repaired.width,
        height: repaired.height,
        maximized: true,
        hasPosition: true,
      ));
      return;
    }
    final bounds = await windowManager.getBounds();
    final repaired = await _repairBounds(bounds);
    widget.controller.updateWindowSnapshot(WindowSnapshot(
      x: repaired.left,
      y: repaired.top,
      width: repaired.width,
      height: repaired.height,
      hasPosition: true,
    ));
  }

  Future<void> _captureNormalBounds() async {
    if (_quitting || !mounted) return;
    try {
      if (await windowManager.isMaximized() ||
          await windowManager.isMinimized()) {
        return;
      }
      final bounds = await windowManager.getBounds();
      if (await windowManager.isMaximized() ||
          await windowManager.isMinimized()) {
        return;
      }
      _lastNormalBounds = bounds;
    } catch (error) {
      debugPrint('记录普通窗口位置失败: $error');
    }
  }

  Future<void> _showWindow() async {
    if (await windowManager.isMinimized()) {
      await windowManager.restore();
    }
    final bounds = await windowManager.getBounds();
    final repaired = await _repairBounds(bounds);
    if (repaired != bounds) await windowManager.setBounds(repaired);
    await windowManager.show();
    await windowManager.focus();
  }

  Future<void> _quit() async {
    if (_quitting) return;
    _quitting = true;
    try {
      await _desktopInitialization;
    } catch (error) {
      debugPrint('等待桌面功能初始化失败: $error');
    }
    try {
      await _saveWindow();
    } catch (error) {
      debugPrint('保存窗口状态失败: $error');
    }
    try {
      await _mediaKeys.unregister();
    } catch (error) {
      debugPrint('媒体键注销失败: $error');
    }
    try {
      await widget.controller.shutdown();
    } catch (error) {
      debugPrint('停止播放失败: $error');
    }
    if (_trayReady) {
      try {
        await trayManager.destroy();
      } catch (error) {
        debugPrint('销毁托盘失败: $error');
      }
    }
    try {
      await windowManager.setPreventClose(false);
    } catch (error) {
      debugPrint('解除窗口关闭拦截失败: $error');
    }
    try {
      await windowManager.destroy();
    } catch (error) {
      debugPrint('销毁窗口失败: $error');
    }
  }

  @override
  void onWindowClose() async {
    if (_quitting) return;
    if (!_trayReady) {
      await _quit();
      return;
    }
    try {
      await _saveWindow();
    } catch (error) {
      debugPrint('保存窗口状态失败: $error');
    }
    try {
      await windowManager.hide();
    } catch (error) {
      debugPrint('隐藏窗口失败: $error');
    }
  }

  @override
  void onWindowMove() {
    _captureNormalBounds();
  }

  @override
  void onWindowMoved() {
    _captureNormalBounds();
  }

  @override
  void onWindowResize() {
    _captureNormalBounds();
  }

  @override
  void onWindowResized() {
    _captureNormalBounds();
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
    widget.controller.actionError.removeListener(_showActionError);
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
      scaffoldMessengerKey: _scaffoldMessengerKey,
      scrollBehavior:
          const MaterialScrollBehavior().copyWith(scrollbars: false),
      theme: MupTheme.material(dark),
      home: Scaffold(
        backgroundColor: Colors.transparent,
        body: Shortcuts(
          shortcuts: const {
            SingleActivator(LogicalKeyboardKey.escape): _BackIntent(),
          },
          child: Actions(
            actions: {
              _BackIntent: CallbackAction<_BackIntent>(
                onInvoke: (_) {
                  if (widget.controller.stage == AppStage.connect) {
                    widget.controller.cancelConnect();
                    return widget.controller.stage == AppStage.ready;
                  }
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
