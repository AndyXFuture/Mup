import 'dart:math' as math;
import 'dart:ui';

const _minVisibleWidth = 120.0;
const _minVisibleHeight = 80.0;

/// Returns [desired] when it is meaningfully visible on a display. Otherwise,
/// centers a size-constrained copy inside the preferred display area.
///
/// Windows uses coordinates around -32000 for minimized/hidden windows. A
/// window in that state is still marked visible and can leave a taskbar button
/// behind, so checking `isVisible` alone is not sufficient.
Rect repairWindowBounds(Rect desired, List<Rect> displayAreas) {
  final usableAreas =
      displayAreas.where((area) => area.width > 0 && area.height > 0).toList();
  if (usableAreas.isEmpty) return desired;

  if (isWindowBoundsVisible(desired, usableAreas)) return desired;

  final target = usableAreas.first;
  final width = math
      .min(
        desired.width > 0 ? desired.width : math.min(1080, target.width),
        target.width,
      )
      .toDouble();
  final height = math
      .min(
        desired.height > 0 ? desired.height : math.min(720, target.height),
        target.height,
      )
      .toDouble();
  return Rect.fromLTWH(
    target.left + (target.width - width) / 2,
    target.top + (target.height - height) / 2,
    width,
    height,
  );
}

bool isWindowBoundsVisible(Rect window, List<Rect> displayAreas) {
  for (final area in displayAreas) {
    final intersection = window.intersect(area);
    if (intersection.width >= math.min(_minVisibleWidth, window.width) &&
        intersection.height >= math.min(_minVisibleHeight, window.height)) {
      return true;
    }
  }
  return false;
}
