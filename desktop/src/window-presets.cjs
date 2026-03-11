const WINDOW_MARGIN = 64;
const IPHONE_MIN_WIDTH = 390;
const IPHONE_MIN_HEIGHT = 844;

const ROUTE_PROFILES = {
  default: {
    // Chat / Focus / Diary default profile: larger canvas for timeline + composer.
    heightRatio: 0.9,
    aspectRatio: 1.34,
    minWidth: 1040,
    minHeight: 760,
  },
  processes: {
    // Mac Activity Monitor style: strongly horizontal.
    heightRatio: 0.84,
    aspectRatio: 1.8,
    minWidth: 1320,
    minHeight: 740,
  },
  settings: {
    heightRatio: 0.9,
    aspectRatio: 1.34,
    minWidth: 1120,
    minHeight: 760,
  },
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getRouteProfile(route) {
  const cleanRoute = String(route || "/").split("?")[0].split("#")[0];
  if (cleanRoute.startsWith("/processes")) return ROUTE_PROFILES.processes;
  if (cleanRoute.startsWith("/settings")) return ROUTE_PROFILES.settings;
  return ROUTE_PROFILES.default;
}

function getWindowPreset(route, area) {
  const safeArea = area || { width: 1440, height: 900 };
  const profile = getRouteProfile(route);
  const maxHeight = Math.max(500, safeArea.height - WINDOW_MARGIN);
  const minHeight = Math.min(IPHONE_MIN_HEIGHT, maxHeight);
  const targetHeight = clamp(Math.round(safeArea.height * profile.heightRatio), minHeight, maxHeight);
  const maxWidth = Math.max(420, safeArea.width - WINDOW_MARGIN);
  const minWidth = Math.min(IPHONE_MIN_WIDTH, maxWidth);

  const mainWidth = clamp(Math.round(targetHeight * profile.aspectRatio), minWidth, maxWidth);
  return {
    width: mainWidth,
    height: targetHeight,
    minWidth,
    minHeight,
    maxWidth,
    maxHeight,
  };
}

module.exports = {
  getWindowPreset,
};
