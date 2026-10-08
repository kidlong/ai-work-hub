import 'package:flutter/material.dart';

/// Bảng màu "bàn làm việc yên tĩnh": nền giấy ấm, mực xanh đậm, điểm nhấn xanh ngọc cho AI.
class AppColors {
  static const ink = Color(0xFF14213D);
  static const teal = Color(0xFF0F766E);
  static const tealSoft = Color(0xFFE6F2F0);
  static const paper = Color(0xFFF6F5F1);
  static const line = Color(0xFFE4E1D9);
  static const muted = Color(0xFF667085);

  static const critical = Color(0xFFB42318);
  static const criticalSoft = Color(0xFFFDECEA);
  static const warning = Color(0xFFB54708);
  static const warningSoft = Color(0xFFFEF4E6);
  static const info = Color(0xFF175CD3);
  static const infoSoft = Color(0xFFEAF1FD);
  static const ok = Color(0xFF067647);

  // Dark
  static const darkBg = Color(0xFF0E1220);
  static const darkCard = Color(0xFF171C2E);
  static const darkLine = Color(0xFF2A3047);
}

class Severity {
  static Color color(String s) => switch (s) {
        'critical' => AppColors.critical,
        'warning' => AppColors.warning,
        _ => AppColors.info,
      };

  static Color soft(String s, Brightness b) {
    if (b == Brightness.dark) return color(s).withValues(alpha: 0.18);
    return switch (s) {
      'critical' => AppColors.criticalSoft,
      'warning' => AppColors.warningSoft,
      _ => AppColors.infoSoft,
    };
  }

  static String bucketSeverity(String bucket) => switch (bucket) {
        'critical' => 'critical',
        'high' => 'warning',
        _ => 'info',
      };
}

ThemeData buildTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.ink,
    brightness: brightness,
    primary: dark ? const Color(0xFF9DB4E8) : AppColors.ink,
    secondary: dark ? const Color(0xFF5FD3C4) : AppColors.teal,
    surface: dark ? AppColors.darkBg : AppColors.paper,
    error: AppColors.critical,
  );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme, brightness: brightness);
  final cardColor = dark ? AppColors.darkCard : Colors.white;
  final lineColor = dark ? AppColors.darkLine : AppColors.line;

  return base.copyWith(
    scaffoldBackgroundColor: scheme.surface,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0.5,
      centerTitle: false,
      titleTextStyle: TextStyle(fontSize: 21, fontWeight: FontWeight.w800, letterSpacing: -0.3, color: scheme.onSurface),
    ),
    cardTheme: CardThemeData(
      color: cardColor,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: lineColor)),
    ),
    dividerTheme: DividerThemeData(color: lineColor, space: 1),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: cardColor,
      indicatorColor: dark ? const Color(0xFF26314F) : AppColors.tealSoft,
      labelTextStyle: WidgetStatePropertyAll(base.textTheme.labelSmall?.copyWith(fontWeight: FontWeight.w600)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: cardColor,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: lineColor)),
      enabledBorder:
          OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: lineColor)),
      focusedBorder:
          OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: scheme.primary, width: 1.5)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(44, 44),
        side: BorderSide(color: lineColor),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      side: BorderSide(color: lineColor),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: dark ? AppColors.darkCard : Colors.white,
      showDragHandle: true,
    ),
  );
}
