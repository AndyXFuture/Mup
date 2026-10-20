import 'package:flutter/material.dart';

import '../theme.dart';

class MupIconButton extends StatefulWidget {
  const MupIconButton({
    super.key,
    required this.icon,
    this.onTap,
    this.size = 34,
    this.iconSize = 16,
    this.color,
    this.tooltip,
    this.filled = false,
  });

  final IconData icon;
  final VoidCallback? onTap;
  final double size;
  final double iconSize;
  final Color? color;
  final String? tooltip;
  final bool filled;

  @override
  State<MupIconButton> createState() => _MupIconButtonState();
}

class _MupIconButtonState extends State<MupIconButton> {
  bool _hover = false;
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final color = widget.color ?? (_hover ? theme.text : theme.muted);
    final body = MouseRegion(
      cursor: widget.onTap == null
          ? SystemMouseCursors.basic
          : SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: widget.onTap == null
            ? null
            : (_) => setState(() => _pressed = true),
        onTapCancel: () => setState(() => _pressed = false),
        onTapUp: widget.onTap == null
            ? null
            : (_) {
                setState(() => _pressed = false);
                widget.onTap!();
              },
        child: AnimatedScale(
          scale: _pressed ? 0.93 : 1,
          duration: const Duration(milliseconds: 120),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            width: widget.size,
            height: widget.size,
            decoration: widget.filled
                ? BoxDecoration(
                    borderRadius: BorderRadius.circular(widget.size * 0.32),
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        theme.rimSoft.withValues(alpha: _hover ? 0.85 : 0.45),
                        theme.rimDark.withValues(alpha: 0.16),
                      ],
                    ),
                    border: Border.all(color: theme.rimSoft),
                  )
                : BoxDecoration(
                    color: _hover ? theme.track : Colors.transparent,
                    borderRadius: BorderRadius.circular(widget.size * 0.32),
                  ),
            child: Icon(widget.icon, size: widget.iconSize, color: color),
          ),
        ),
      ),
    );
    return widget.tooltip == null
        ? body
        : Tooltip(message: widget.tooltip!, child: body);
  }
}

class MupTextButton extends StatefulWidget {
  const MupTextButton({
    super.key,
    required this.label,
    this.icon,
    this.onTap,
    this.primary = false,
    this.iconOnly = false,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final bool primary;
  final bool iconOnly;

  @override
  State<MupTextButton> createState() => _MupTextButtonState();
}

class _MupTextButtonState extends State<MupTextButton> {
  bool _hover = false;
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final color = widget.primary ? Colors.white : theme.text;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (_) => setState(() => _pressed = true),
        onTapCancel: () => setState(() => _pressed = false),
        onTapUp: (_) {
          setState(() => _pressed = false);
          widget.onTap?.call();
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 160),
          height: 34,
          width: widget.iconOnly ? 34 : null,
          padding: widget.iconOnly
              ? EdgeInsets.zero
              : const EdgeInsets.symmetric(horizontal: 15),
          transform:
              Matrix4.translationValues(0, _pressed ? 0 : (_hover ? -1 : 0), 0),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(11),
            gradient: widget.primary
                ? const LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [Color(0xFF7672FF), Color(0xFF5752D9)],
                  )
                : LinearGradient(
                    colors: [theme.surfaceTop, theme.surfaceBottom]),
            border: Border.all(
              color: widget.primary
                  ? Colors.white.withValues(alpha: 0.16)
                  : (_hover
                      ? theme.primaryLight.withValues(alpha: 0.35)
                      : theme.rimSoft),
            ),
            boxShadow: [
              BoxShadow(
                color: widget.primary
                    ? theme.primary.withValues(alpha: 0.55)
                    : theme.shadow.withValues(alpha: theme.dark ? 0.25 : 0.08),
                blurRadius: widget.primary ? 18 : 12,
                offset: const Offset(0, 6),
                spreadRadius: -4,
              ),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (widget.icon != null)
                Icon(widget.icon, size: 14, color: color),
              if (widget.icon != null && !widget.iconOnly)
                const SizedBox(width: 7),
              if (!widget.iconOnly)
                Text(
                  widget.label,
                  style: TextStyle(
                    color: color,
                    fontSize: 12.5,
                    fontWeight:
                        widget.primary ? FontWeight.w600 : FontWeight.w500,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class GlowToggle extends StatelessWidget {
  const GlowToggle({
    super.key,
    required this.value,
    required this.onChanged,
  });

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return GestureDetector(
      onTap: () => onChanged(!value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        width: 42,
        height: 24,
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          gradient: value
              ? LinearGradient(colors: [theme.primary, theme.primaryLight])
              : null,
          color: value ? null : theme.track,
          boxShadow: value
              ? [
                  BoxShadow(
                    color: theme.primary.withValues(alpha: 0.42),
                    blurRadius: 12,
                  ),
                ]
              : null,
        ),
        child: AnimatedAlign(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          alignment: value ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            width: 18,
            height: 18,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: value ? Colors.white : theme.muted,
              boxShadow: const [
                BoxShadow(
                    color: Color(0x40000000),
                    blurRadius: 4,
                    offset: Offset(0, 1)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
