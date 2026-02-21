const MAIN_HEIGHT_RATIO = 2 / 3;
const MAIN_ASPECT_RATIO = 9 / 19.5;
const PROCESS_ASPECT_RATIO = 4 / 3;
const WINDOW_MARGIN = 72;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizeRoute(route = "/") {
  const raw = String(route || "").trim() || "/";
  return raw.startsWith("/") ? raw : `/${raw}`;
}

function getWindowPreset(route, area) {
  const safeArea = area || { width: 1440, height: 900 };
  const maxHeight = Math.max(500, safeArea.height - WINDOW_MARGIN);
  const targetHeight = clamp(Math.round(safeArea.height * MAIN_HEIGHT_RATIO), 500, maxHeight);
  const maxWidth = Math.max(420, safeArea.width - WINDOW_MARGIN);
  const normalized = normalizeRoute(route);

  if (normalized.startsWith("/processes")) {
    const processWidth = clamp(Math.round(targetHeight * PROCESS_ASPECT_RATIO), 720, maxWidth);
    return {
      width: processWidth,
      height: targetHeight,
      minWidth: processWidth,
      minHeight: targetHeight,
      maxWidth: processWidth,
      maxHeight: targetHeight,
    };
  }

  const mainWidth = clamp(Math.round(targetHeight * MAIN_ASPECT_RATIO), 360, maxWidth);
  return {
    width: mainWidth,
    height: targetHeight,
    minWidth: mainWidth,
    minHeight: targetHeight,
    maxWidth: mainWidth,
    maxHeight: targetHeight,
  };
}

module.exports = {
  getWindowPreset,
};

