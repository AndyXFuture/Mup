import 'package:flutter/material.dart';

@immutable
class MupTheme extends ThemeExtension<MupTheme> {
  const MupTheme({
    required this.dark,
    required this.backgroundTop,
    required this.backgroundBottom,
    required this.ambient,
    required this.surfaceTop,
    required this.surfaceBottom,
    required this.surfaceAltTop,
    required this.surfaceAltBottom,
    required this.text,
    required this.muted,
    required this.dim,
    required this.primary,
    required this.primaryLight,
    required this.primaryText,
    required this.primarySoft,
    required this.danger,
    required this.rimLight,
    required this.rimSoft,
    required this.rimDark,
    required this.track,
    required this.separator,
    required this.shadow,
  });

  final bool dark;
  final Color backgroundTop;
  final Color backgroundBottom;
  final Color ambient;
  final Color surfaceTop;
  final Color surfaceBottom;
  final Color surfaceAltTop;
  final Color surfaceAltBottom;
  final Color text;
  final Color muted;
  final Color dim;
  final Color primary;
  final Color primaryLight;
  final Color primaryText;
  final Color primarySoft;
  final Color danger;
  final Color rimLight;
  final Color rimSoft;
  final Color rimDark;
  final Color track;
  final Color separator;
  final Color shadow;

  static const darkTheme = MupTheme(
    dark: true,
    backgroundTop: Color(0xFF1B1C24),
    backgroundBottom: Color(0xFF0F1015),
    ambient: Color(0x336054F1),
    surfaceTop: Color(0xAA22242E),
    surfaceBottom: Color(0xCD14151C),
    surfaceAltTop: Color(0x881C1E27),
    surfaceAltBottom: Color(0xD912131A),
    text: Color(0xFFEEF0F6),
    muted: Color(0xFF9AA0AD),
    dim: Color(0xFF6F7480),
    primary: Color(0xFF6A66F5),
    primaryLight: Color(0xFF8F8BFF),
    primaryText: Color(0xFFC9C8FF),
    primarySoft: Color(0x332B2C55),
    danger: Color(0xFFEF6F8F),
    rimLight: Color(0x2EFFFFFF),
    rimSoft: Color(0x12FFFFFF),
    rimDark: Color(0x8C000000),
    track: Color(0x14FFFFFF),
    separator: Color(0x0BFFFFFF),
    shadow: Color(0x8C000000),
  );

  static const lightTheme = MupTheme(
    dark: false,
    backgroundTop: Color(0xFFFBFBFF),
    backgroundBottom: Color(0xFFEEF0F7),
    ambient: Color(0x246054F1),
    surfaceTop: Color(0xB8FFFFFF),
    surfaceBottom: Color(0xCCF4F6FC),
    surfaceAltTop: Color(0xCFFFFFFF),
    surfaceAltBottom: Color(0xD6F2F3FA),
    text: Color(0xFF1A1B22),
    muted: Color(0xFF5F6470),
    dim: Color(0xFF8A8F9C),
    primary: Color(0xFF4F4BD6),
    primaryLight: Color(0xFF7A76FF),
    primaryText: Color(0xFF3F3CC0),
    primarySoft: Color(0xFFE7E6FF),
    danger: Color(0xFFD94A6A),
    rimLight: Color(0xFAFFFFFF),
    rimSoft: Color(0xA6FFFFFF),
    rimDark: Color(0x101A1B22),
    track: Color(0x141A1B22),
    separator: Color(0x0F1A1B22),
    shadow: Color(0x29444064),
  );

  LinearGradient get panelGradient => LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [surfaceTop, surfaceBottom],
      );

  LinearGradient get altPanelGradient => LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [surfaceAltTop, surfaceAltBottom],
      );

  LinearGradient get backgroundGradient => LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [backgroundTop, backgroundBottom],
      );

  static MupTheme of(BuildContext context) =>
      Theme.of(context).extension<MupTheme>() ?? darkTheme;

  static ThemeData material(bool dark) {
    final palette = dark ? darkTheme : lightTheme;
    return ThemeData(
      brightness: dark ? Brightness.dark : Brightness.light,
      useMaterial3: true,
      scaffoldBackgroundColor: palette.backgroundBottom,
      fontFamily: 'Microsoft YaHei UI',
      fontFamilyFallback: const ['Microsoft YaHei', 'Segoe UI'],
      colorScheme: ColorScheme.fromSeed(
        seedColor: palette.primary,
        brightness: dark ? Brightness.dark : Brightness.light,
      ),
      splashFactory: NoSplash.splashFactory,
      highlightColor: Colors.transparent,
      hoverColor: Colors.transparent,
      textSelectionTheme: TextSelectionThemeData(
        cursorColor: palette.primaryLight,
        selectionColor: palette.primary.withValues(alpha: 0.28),
        selectionHandleColor: palette.primaryLight,
      ),
      extensions: [palette],
    );
  }

  @override
  MupTheme copyWith() => this;

  @override
  MupTheme lerp(ThemeExtension<MupTheme>? other, double t) {
    if (other is! MupTheme) return this;
    Color mix(Color a, Color b) => Color.lerp(a, b, t)!;
    return MupTheme(
      dark: t < 0.5 ? dark : other.dark,
      backgroundTop: mix(backgroundTop, other.backgroundTop),
      backgroundBottom: mix(backgroundBottom, other.backgroundBottom),
      ambient: mix(ambient, other.ambient),
      surfaceTop: mix(surfaceTop, other.surfaceTop),
      surfaceBottom: mix(surfaceBottom, other.surfaceBottom),
      surfaceAltTop: mix(surfaceAltTop, other.surfaceAltTop),
      surfaceAltBottom: mix(surfaceAltBottom, other.surfaceAltBottom),
      text: mix(text, other.text),
      muted: mix(muted, other.muted),
      dim: mix(dim, other.dim),
      primary: mix(primary, other.primary),
      primaryLight: mix(primaryLight, other.primaryLight),
      primaryText: mix(primaryText, other.primaryText),
      primarySoft: mix(primarySoft, other.primarySoft),
      danger: mix(danger, other.danger),
      rimLight: mix(rimLight, other.rimLight),
      rimSoft: mix(rimSoft, other.rimSoft),
      rimDark: mix(rimDark, other.rimDark),
      track: mix(track, other.track),
      separator: mix(separator, other.separator),
      shadow: mix(shadow, other.shadow),
    );
  }
}
