import 'dart:io';

import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../theme.dart';

class CoverArt extends StatelessWidget {
  const CoverArt({
    super.key,
    required this.url,
    this.size = 48,
    this.radius = 12,
    this.glow = false,
  });

  final String url;
  final double size;
  final double radius;
  final bool glow;

  @override
  Widget build(BuildContext context) {
    final theme = MupTheme.of(context);
    final base = ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: theme.dark
                ? const [Color(0x754E5166), Color(0x85262832)]
                : const [Color(0xFFF4F5FB), Color(0xFFE3E5F2)],
          ),
          border: Border.all(color: theme.rimSoft),
        ),
        child: url.isEmpty ? _placeholder(theme) : _image(theme),
      ),
    );
    if (!glow) return base;
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius + 2),
        boxShadow: [
          BoxShadow(
            color: theme.primary.withValues(alpha: 0.42),
            blurRadius: 36,
            spreadRadius: -2,
            offset: const Offset(0, 16),
          ),
        ],
      ),
      child: base,
    );
  }

  Widget _placeholder(MupTheme theme) => Center(
        child: Icon(
          LucideIcons.music4,
          size: size * 0.36,
          color: theme.dark ? const Color(0xFF8E92C8) : const Color(0xFF7C80B8),
        ),
      );

  Widget _image(MupTheme theme) {
    if (url.startsWith('asset:')) {
      return Image.asset(
        url.substring('asset:'.length),
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _placeholder(theme),
      );
    }
    if (File(url).existsSync()) {
      return Image.file(
        key: ValueKey('file:$url'),
        File(url),
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _placeholder(theme),
      );
    }
    return Image.network(
      key: ValueKey('network:$url'),
      url,
      width: size,
      height: size,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => _placeholder(theme),
      loadingBuilder: (context, child, progress) =>
          progress == null ? child : _placeholder(theme),
    );
  }
}
