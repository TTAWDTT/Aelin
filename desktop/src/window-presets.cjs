const MAIN_HEIGHT_RATIO = 3 / 4;
const MAIN_ASPECT_RATIO = 9 / 16;
const WINDOW_MARGIN = 72;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getWindowPreset(_route, area) {
  const safeArea = area || { width: 1440, height: 900 };
  const maxHeight = Math.max(500, safeArea.height - WINDOW_MARGIN);
  const targetHeight = clamp(Math.round(safeArea.height * MAIN_HEIGHT_RATIO), 500, maxHeight);
  const maxWidth = Math.max(420, safeArea.width - WINDOW_MARGIN);

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
