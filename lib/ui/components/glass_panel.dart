import 'dart:ui';

import 'package:flutter/material.dart';

import '../theme.dart';

class GlassPanel extends StatelessWidget {
  const GlassPanel({
    super.key,
    required this.child,
    this.padding = EdgeInsets.zero,
    this.radius = 18,
    this.alt = false,
    this.blur = 18,
    this.shadow = true,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;
  final bool alt;
  final double blur;
  final bool shadow;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final borderRadius = BorderRadius.circular(radius);
    final gradient = alt ? theme.altPanelGradient : theme.panelGradient;
    return Container(
      decoration: BoxDecoration(
        borderRadius: borderRadius,
        boxShadow: shadow
            ? [
                BoxShadow(
                  color:
                      theme.shadow.withValues(alpha: theme.dark ? 0.38 : 0.12),
                  blurRadius: 32,
                  spreadRadius: -16,
                  offset: const Offset(0, 20),
                ),
              ]
            : null,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: borderRadius,
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [theme.rimLight, theme.rimSoft, theme.rimDark],
            stops: const [0, 0.42, 1],
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(1),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(radius - 1),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(radius - 1),
                  gradient: gradient,
                ),
                child: Padding(padding: padding, child: child),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class PanelOverlay extends StatelessWidget {
  const PanelOverlay({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Stack(
        fit: StackFit.expand,
        children: [
          const IgnorePointer(child: _RimGlow()),
          child,
        ],
      );
}

class _RimGlow extends StatelessWidget {
  const _RimGlow();

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return CustomPaint(painter: _RimPainter(theme.rimLight));
  }
}

class _RimPainter extends CustomPainter {
  const _RimPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..strokeWidth = 1
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [color.withValues(alpha: 0.65), color.withValues(alpha: 0.02)],
      ).createShader(Offset.zero & size);
    final rect = (Offset.zero & size).deflate(0.5);
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(17.5)),
      paint..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(covariant _RimPainter oldDelegate) =>
      oldDelegate.color != color;
}

class GlowDivider extends StatelessWidget {
  const GlowDivider({super.key, this.width = 380});

  final double width;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    return SizedBox(
      width: width,
      height: 48,
      child: CustomPaint(
        painter: _GlowDividerPainter(
          primary: theme.primary,
          light: theme.primaryLight,
        ),
      ),
    );
  }
}

class _GlowDividerPainter extends CustomPainter {
  const _GlowDividerPainter({required this.primary, required this.light});

  final Color primary;
  final Color light;

  @override
  void paint(Canvas canvas, Size size) {
    final centerY = size.height / 2;
    final rect = Rect.fromLTWH(0, centerY - 1, size.width, 2);
    final shader = LinearGradient(
      colors: [
        Colors.transparent,
        primary.withValues(alpha: 0.04),
        primary.withValues(alpha: 0.20),
        light.withValues(alpha: 0.58),
        light.withValues(alpha: 0.58),
        primary.withValues(alpha: 0.20),
        primary.withValues(alpha: 0.04),
        Colors.transparent,
      ],
      stops: const [0, 0.08, 0.24, 0.40, 0.60, 0.76, 0.92, 1],
    ).createShader(rect);

    final wideHalo = Paint()
      ..shader = shader
      ..style = PaintingStyle.stroke
      ..strokeWidth = 14
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 26);
    canvas.drawLine(
      Offset(0, centerY),
      Offset(size.width, centerY),
      wideHalo,
    );

    final halo = Paint()
      ..shader = shader
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 9);
    canvas.drawLine(Offset(0, centerY), Offset(size.width, centerY), halo);

    final line = Paint()
      ..shader = shader
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    canvas.drawLine(Offset(0, centerY), Offset(size.width, centerY), line);
  }

  @override
  bool shouldRepaint(covariant _GlowDividerPainter oldDelegate) =>
      oldDelegate.primary != primary || oldDelegate.light != light;
}
