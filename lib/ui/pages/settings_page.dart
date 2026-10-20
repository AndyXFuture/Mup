import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../../core/app_controller.dart';
import '../components/controls.dart';
import '../components/glass_panel.dart';
import '../theme.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key, required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final config = controller.config;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(24, 4, 24, 20),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: GlassPanel(
            padding: const EdgeInsets.fromLTRB(26, 22, 26, 18),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    MupIconButton(
                      icon: LucideIcons.arrowLeft,
                      size: 32,
                      iconSize: 16,
                      onTap: controller.openLibrary,
                      tooltip: '返回曲库',
                    ),
                    const SizedBox(width: 10),
                    Text(
                      '设置',
                      style: TextStyle(
                        color: theme.text,
                        fontSize: 22,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '所有改动即时生效',
                  style: TextStyle(color: theme.muted, fontSize: 12),
                ),
                const SizedBox(height: 14),
                _SettingsRow(
                  title: '连接设置',
                  hint: '${config.host}:${config.port} · ${config.username}',
                  trailing: MupTextButton(
                    label: '重新填写',
                    onTap: controller.openConnect,
                  ),
                ),
                _SettingsRow(
                  title: '外观主题',
                  hint: '跟随系统会自动切换深浅色',
                  trailing: _ThemeSegment(
                    value: config.themeMode,
                    onChanged: controller.setThemeMode,
                  ),
                ),
                _SettingsRow(
                  title: '减少动效',
                  hint: '关闭过渡动画，适合低配设备',
                  trailing: GlowToggle(
                    value: config.reduceMotion,
                    onChanged: controller.setReduceMotion,
                  ),
                ),
                _SettingsRow(
                  title: '开机自启',
                  hint: '登录 Windows 后在托盘静默启动',
                  trailing: GlowToggle(
                    value: config.autostart,
                    onChanged: (value) async {
                      final success = await controller.setAutostart(value);
                      if (!success && context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('无法修改启动项，请检查系统权限')),
                        );
                      }
                    },
                  ),
                ),
                const _SettingsRow(
                  title: '快捷键',
                  hint: '系统媒体键 · 全局组合键',
                  trailing: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    alignment: WrapAlignment.end,
                    children: [
                      _Chip('Ctrl Alt P'),
                      _Chip('Ctrl Alt ←'),
                      _Chip('Ctrl Alt →'),
                    ],
                  ),
                ),
                _SettingsRow(
                  title: '关于',
                  hint: 'Flutter · Subsonic / Jellyfin',
                  trailing: Text(
                    'v0.4.0',
                    style: TextStyle(color: theme.muted, fontSize: 11.5),
                  ),
                  last: true,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SettingsRow extends StatelessWidget {
  const _SettingsRow({
    required this.title,
    required this.hint,
    required this.trailing,
    this.last = false,
  });

  final String title;
  final String hint;
  final Widget trailing;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Container(
      constraints: const BoxConstraints(minHeight: 70),
      padding: const EdgeInsets.symmetric(vertical: 13),
      decoration: BoxDecoration(
        border:
            last ? null : Border(bottom: BorderSide(color: theme.separator)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    color: theme.text,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  hint,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: theme.muted, fontSize: 11),
                ),
              ],
            ),
          ),
          const SizedBox(width: 20),
          trailing,
        ],
      ),
    );
  }
}

class _ThemeSegment extends StatelessWidget {
  const _ThemeSegment({required this.value, required this.onChanged});

  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    const options = [
      ('system', '跟随系统'),
      ('light', '浅色'),
      ('dark', '深色'),
    ];
    return Container(
      height: 32,
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: theme.track,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final (key, label) in options)
            GestureDetector(
              onTap: () => onChanged(key),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                padding: const EdgeInsets.symmetric(horizontal: 10),
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: value == key
                      ? theme.primary.withValues(alpha: 0.80)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(7),
                ),
                child: Text(
                  label,
                  style: TextStyle(
                    color: value == key ? Colors.white : theme.muted,
                    fontSize: 10.5,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(7),
        color: theme.track,
        border: Border.all(color: theme.rimSoft),
      ),
      child: Text(label, style: TextStyle(color: theme.muted, fontSize: 10)),
    );
  }
}
