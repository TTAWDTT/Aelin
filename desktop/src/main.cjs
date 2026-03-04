const { app, BrowserWindow, Menu, Tray, dialog, ipcMain, screen, powerMonitor, desktopCapturer } = require("electron");
const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const { StringDecoder } = require("string_decoder");
const { pathToFileURL } = require("url");
const { getWindowPreset } = require("./window-presets.cjs");
const {
  MUSIC_PROCESS_TOKENS,
  WORK_PROCESS_TOKENS,
  buildWorkNarration,
  displayProcessName,
  normalizeProcessToken,
  uniqueDisplayNames,
} = require("./pet-process-utils.cjs");
const { DEFAULT_BEHAVIOR, loadPetBehaviorConfig } = require("./pet-behavior.cjs");
const { computePetEmotion } = require("./pet-emotion-engine.cjs");

const isDev = process.env.MERCURYDESK_DESKTOP_DEV === "1" || !app.isPackaged;
const backendPort = Number(process.env.MERCURYDESK_BACKEND_PORT || (isDev ? 8000 : 18080));
const frontendPort = Number(process.env.MERCURYDESK_DESKTOP_PORT || (isDev ? 5173 : 1420));
const desktopZoom = Number(process.env.MERCURYDESK_DESKTOP_ZOOM || "1.0");
const PET_COMPACT_WINDOW_SIZE = 128;
const PET_EXPANDED_WINDOW_WIDTH = 236;
const PET_EXPANDED_WINDOW_MAX_HEIGHT = 420;
const MAIN_ZOOM_MIN = 0.5;
const MAIN_ZOOM_MAX = 2.0;
const MAIN_ZOOM_STEP = 0.1;
const APP_USER_MODEL_ID = "com.ttawdtt.aelin";
const PET_DEBUG_LOG_ENABLED = process.env.AELIN_PET_DEBUG === "1";
const PET_PLUGIN_API_ENABLED = process.env.AELIN_PET_PLUGIN_API_DISABLED !== "1";
const PET_PLUGIN_API_TOKEN = String(process.env.AELIN_PET_PLUGIN_TOKEN || "").trim();

if (process.platform === "win32") {
  app.setAppUserModelId(APP_USER_MODEL_ID);
}

let mainWindow = null;
let petWindow = null;
let tray = null;
let backendProc = null;
let frontendDevProc = null;
let frontendServer = null;
let closing = false;
let petDragState = null;
let petDragTimer = null;
let petIpcHandlersRegistered = false;
let petPointerActive = false;
let petVisible = true;
let petClickThroughEnabled = true;
let petStateAssets = {};
let petStateTimer = null;
let petHoverGuardTimer = null;
let petStateLastKey = "";
let petLastState = "happy";
let petCpuSnapshot = null;
let petPowerEventsBound = false;
let mainWindowPinned = false;
let petWorkingPhase = false;
let petCompletionUntil = 0;
let petWorkStartedAt = 0;
let petCoachLine = "";
let petCoachReason = "";
let petCoachLineUntil = 0;
let petCoachCooldownUntil = 0;
let petCoachPending = false;
let petLateNightHintDate = "";
let petProcessProbeCache = {
  ts: 0,
  names: new Set(),
  error: "",
  inFlight: false,
};
let petMediaCache = {
  ts: 0,
  snapshot: null,
  error: "",
  inFlight: false,
};
let petVolumeEstimate = 50;
let petLayoutState = {
  mode: "compact",
  width: PET_COMPACT_WINDOW_SIZE,
  height: PET_COMPACT_WINDOW_SIZE,
  anchorX: PET_COMPACT_WINDOW_SIZE / 2,
  anchorY: PET_COMPACT_WINDOW_SIZE / 2,
};
let petHoverGuardOutsideCount = 0;
let petBehaviorConfig = JSON.parse(JSON.stringify(DEFAULT_BEHAVIOR));
let petBehaviorLoadedFrom = "";
let petEmotionOverride = null;
let petLastRuntimeState = null;
let petPluginApiServer = null;
let petPluginApiPort = 0;
let petPluginLastEvent = null;
let stdioErrorGuardsInstalled = false;

function installStdioErrorGuards() {
  if (stdioErrorGuardsInstalled) return;
  stdioErrorGuardsInstalled = true;
  const suppressBrokenPipe = (error) => {
    const code = String(error?.code || "");
    return code === "EPIPE" || code === "ERR_STREAM_DESTROYED";
  };
  const streams = [process.stdout, process.stderr];
  for (const stream of streams) {
    if (!stream || typeof stream.on !== "function") continue;
    stream.on("error", (error) => {
      if (suppressBrokenPipe(error)) return;
      try {
        const fallback = process.stderr;
        if (fallback && !fallback.destroyed && !fallback.writableEnded && fallback.writable !== false) {
          fallback.write(`[aelin-stream-error] ${String(error?.message || error)}\n`);
        }
      } catch {
        // ignore nested stream failures
      }
    });
  }
}

function safeConsoleLog(message) {
  const line = String(message ?? "");
  const out = process.stdout;
  if (!out) return;
  if (out.destroyed || out.writableEnded || out.writable === false) return;
  try {
    out.write(`${line}\n`);
  } catch (error) {
    const code = String(error?.code || "");
    if (code !== "EPIPE" && code !== "ERR_STREAM_DESTROYED") {
      try {
        const errOut = process.stderr;
        if (errOut && !errOut.destroyed && !errOut.writableEnded && errOut.writable !== false) {
          errOut.write(`[aelin-log-error] ${String(error?.message || error)}\n`);
        }
      } catch {
        // ignore stderr write failures
      }
    }
  }
}

installStdioErrorGuards();

function petDebugLog(tag, payload = {}) {
  if (!PET_DEBUG_LOG_ENABLED) return;
  const stamp = new Date().toISOString();
  let body = "";
  try {
    body = JSON.stringify(payload || {});
  } catch {
    body = "{\"detail\":\"stringify_failed\"}";
  }
  const suffix = body && body !== "{}" ? ` ${body}` : "";
  safeConsoleLog(`[pet-debug ${stamp}] ${String(tag || "event")}${suffix}`);
}

function nowLocalDateStamp(ts) {
  const date = new Date(ts);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function cloneBehaviorDefaults() {
  return JSON.parse(JSON.stringify(DEFAULT_BEHAVIOR));
}

function getBehaviorRoot() {
  const raw = petBehaviorConfig;
  return raw && typeof raw === "object" ? raw : cloneBehaviorDefaults();
}

function getBehaviorNumber(pathParts, fallback, options = {}) {
  const parts = Array.isArray(pathParts) ? pathParts : [];
  let cursor = getBehaviorRoot();
  for (const part of parts) {
    if (!cursor || typeof cursor !== "object") {
      cursor = undefined;
      break;
    }
    cursor = cursor[part];
  }
  const raw = Number(cursor);
  const min = Number.isFinite(options.min) ? Number(options.min) : Number.NEGATIVE_INFINITY;
  const max = Number.isFinite(options.max) ? Number(options.max) : Number.POSITIVE_INFINITY;
  const base = Number.isFinite(raw) ? raw : Number(fallback);
  const clamped = Math.max(min, Math.min(max, base));
  return options.integer ? Math.round(clamped) : clamped;
}

function getStateCompletionHoldMs() {
  return getBehaviorNumber(["state", "completionHoldMs"], DEFAULT_BEHAVIOR.state.completionHoldMs, {
    min: 5_000,
    max: 8 * 60 * 60 * 1000,
    integer: true,
  });
}

function getLateNightStartHour() {
  return getBehaviorNumber(["state", "lateNightStartHour"], DEFAULT_BEHAVIOR.state.lateNightStartHour, {
    min: 0,
    max: 23,
    integer: true,
  });
}

function getLateNightEndHour() {
  return getBehaviorNumber(["state", "lateNightEndHour"], DEFAULT_BEHAVIOR.state.lateNightEndHour, {
    min: 0,
    max: 23,
    integer: true,
  });
}

function isWithinLateNightWindow(hour) {
  const value = Math.max(0, Math.min(23, Math.floor(Number(hour || 0))));
  const start = getLateNightStartHour();
  const end = getLateNightEndHour();
  if (start === end) return true;
  if (start < end) return value >= start && value <= end;
  return value >= start || value <= end;
}

function getCoachLongFocusTriggerMin() {
  return getBehaviorNumber(["coach", "longFocusTriggerMin"], DEFAULT_BEHAVIOR.coach.longFocusTriggerMin, {
    min: 1,
    max: 12 * 60,
    integer: true,
  });
}

function getCoachCooldownMs() {
  return getBehaviorNumber(["coach", "cooldownMs"], DEFAULT_BEHAVIOR.coach.cooldownMs, {
    min: 5_000,
    max: 12 * 60 * 60 * 1000,
    integer: true,
  });
}

function getCoachVisibleMs() {
  return getBehaviorNumber(["coach", "visibleMs"], DEFAULT_BEHAVIOR.coach.visibleMs, {
    min: 5_000,
    max: 12 * 60 * 60 * 1000,
    integer: true,
  });
}

function getHoverGuardIntervalMs() {
  return getBehaviorNumber(["hoverGuard", "intervalMs"], DEFAULT_BEHAVIOR.hoverGuard.intervalMs, {
    min: 40,
    max: 5_000,
    integer: true,
  });
}

function getHoverGuardMarginPx() {
  return getBehaviorNumber(["hoverGuard", "marginPx"], DEFAULT_BEHAVIOR.hoverGuard.marginPx, {
    min: 0,
    max: 240,
    integer: true,
  });
}

function getHoverGuardOutsideTicks() {
  return getBehaviorNumber(["hoverGuard", "outsideTicks"], DEFAULT_BEHAVIOR.hoverGuard.outsideTicks, {
    min: 1,
    max: 60,
    integer: true,
  });
}

function getStatePushIntervalMs() {
  return getBehaviorNumber(["ticker", "statePushIntervalMs"], DEFAULT_BEHAVIOR.ticker.statePushIntervalMs, {
    min: 120,
    max: 20_000,
    integer: true,
  });
}

function getProcessProbeCacheMs() {
  return getBehaviorNumber(["ticker", "processProbeCacheMs"], DEFAULT_BEHAVIOR.ticker.processProbeCacheMs, {
    min: 250,
    max: 20_000,
    integer: true,
  });
}

function getMediaProbeCacheMs() {
  return getBehaviorNumber(["ticker", "mediaProbeCacheMs"], DEFAULT_BEHAVIOR.ticker.mediaProbeCacheMs, {
    min: 250,
    max: 20_000,
    integer: true,
  });
}

function getProbeCommandTimeoutMs() {
  return getBehaviorNumber(["probe", "commandTimeoutMs"], DEFAULT_BEHAVIOR.probe.commandTimeoutMs, {
    min: 1_000,
    max: 120_000,
    integer: true,
  });
}

function reloadPetBehaviorConfig() {
  try {
    const defaultPath = path.join(__dirname, "pet-behavior.json");
    const options = {
      envPath: process.env.AELIN_PET_BEHAVIOR_CONFIG || "",
      userDataPath: app.getPath("userData"),
      defaultPath,
      resourcesPath: process.resourcesPath,
      isPackaged: app.isPackaged,
    };
    const loaded = loadPetBehaviorConfig(options);
    petBehaviorConfig = loaded?.config && typeof loaded.config === "object"
      ? loaded.config
      : cloneBehaviorDefaults();
    petBehaviorLoadedFrom = String(loaded?.loadedFrom || "");
    petDebugLog("main:behavior-config-loaded", {
      from: petBehaviorLoadedFrom || "default",
    });
  } catch (error) {
    petBehaviorConfig = cloneBehaviorDefaults();
    petBehaviorLoadedFrom = "";
    petDebugLog("main:behavior-config-fallback", {
      reason: error instanceof Error ? error.message : String(error || "unknown"),
    });
  }
}

function getActivePetEmotionOverride(nowTs = Date.now()) {
  if (!petEmotionOverride || typeof petEmotionOverride !== "object") return null;
  const expiresAt = Number(petEmotionOverride.expiresAt || 0);
  if (Number.isFinite(expiresAt) && expiresAt > 0 && nowTs >= expiresAt) {
    petEmotionOverride = null;
    return null;
  }
  return {
    mood: petEmotionOverride.mood,
    valence: petEmotionOverride.valence,
    energy: petEmotionOverride.energy,
    focus: petEmotionOverride.focus,
    tension: petEmotionOverride.tension,
    label: petEmotionOverride.label,
    reason: petEmotionOverride.reason,
  };
}

function parsePluginApiPort() {
  const raw = Number(process.env.AELIN_PET_PLUGIN_PORT || 21914);
  if (!Number.isFinite(raw)) return 21914;
  const normalized = Math.round(raw);
  if (normalized === 0) return 0;
  if (normalized < 1024 || normalized > 65535) return 21914;
  return normalized;
}

function normalizeEmotionOverrideInput(payload = {}) {
  const raw = payload && typeof payload === "object" ? payload : {};
  const parseNumberField = (name) => {
    const num = Number(raw[name]);
    if (!Number.isFinite(num)) return undefined;
    return Math.max(0, Math.min(100, Math.round(num)));
  };
  const mood = String(raw.mood || "").trim();
  const label = String(raw.label || "").trim();
  const reason = String(raw.reason || "").trim();
  const ttlRaw = Number(raw.ttlMs);
  const ttlMs = Number.isFinite(ttlRaw) ? Math.max(0, Math.min(24 * 60 * 60 * 1000, Math.round(ttlRaw))) : 0;
  const patch = {
    mood: mood || undefined,
    label: label || undefined,
    reason: reason || undefined,
    valence: parseNumberField("valence"),
    energy: parseNumberField("energy"),
    focus: parseNumberField("focus"),
    tension: parseNumberField("tension"),
  };
  const hasValue = Object.values(patch).some((item) => item !== undefined);
  return {
    hasValue,
    patch,
    ttlMs,
  };
}

function setPetEmotionOverride(payload = {}) {
  const normalized = normalizeEmotionOverrideInput(payload);
  if (!normalized.hasValue) {
    return { ok: false, detail: "empty_override" };
  }
  const nowTs = Date.now();
  petEmotionOverride = {
    ...normalized.patch,
    setAt: nowTs,
    expiresAt: normalized.ttlMs > 0 ? nowTs + normalized.ttlMs : 0,
  };
  pushPetState(true);
  return {
    ok: true,
    override: {
      ...petEmotionOverride,
    },
  };
}

function clearPetEmotionOverride() {
  if (!petEmotionOverride) {
    return { ok: true, changed: false };
  }
  petEmotionOverride = null;
  pushPetState(true);
  return { ok: true, changed: true };
}

function createPluginApiAuthMiddleware() {
  if (!PET_PLUGIN_API_TOKEN) {
    return (_req, _res, next) => next();
  }
  return (req, res, next) => {
    const authHeader = String(req.headers.authorization || "").trim();
    const tokenHeader = String(req.headers["x-aelin-token"] || "").trim();
    const bearer = authHeader.toLowerCase().startsWith("bearer ")
      ? authHeader.slice(7).trim()
      : "";
    const provided = tokenHeader || bearer;
    if (provided && provided === PET_PLUGIN_API_TOKEN) {
      next();
      return;
    }
    res.status(401).json({
      ok: false,
      detail: "unauthorized",
    });
  };
}

function buildPetPluginStateSnapshot(forceRefresh = false) {
  const hasCachedState = petLastRuntimeState && typeof petLastRuntimeState === "object";
  const latest = forceRefresh || !hasCachedState
    ? computePetRuntimeState()
    : petLastRuntimeState;
  petLastRuntimeState = latest;
  return {
    ...latest,
    behaviorSource: petBehaviorLoadedFrom || "default",
    pluginEvent: petPluginLastEvent || null,
  };
}

function clampNumber(value, fallback, min, max) {
  const parsed = Number(value);
  const base = Number.isFinite(parsed) ? parsed : Number(fallback);
  const floor = Number.isFinite(Number(min)) ? Number(min) : Number.NEGATIVE_INFINITY;
  const ceil = Number.isFinite(Number(max)) ? Number(max) : Number.POSITIVE_INFINITY;
  return Math.max(floor, Math.min(ceil, base));
}

function resolveCaptureDisplay(payload = {}) {
  const displays = screen.getAllDisplays();
  if (!Array.isArray(displays) || displays.length === 0) {
    return screen.getPrimaryDisplay() || null;
  }
  const requestedId = String(payload?.display_id || payload?.displayId || "").trim();
  if (requestedId) {
    const matched = displays.find((item) => String(item?.id || "") === requestedId);
    if (matched) return matched;
  }
  return screen.getPrimaryDisplay() || displays[0] || null;
}

async function captureScreenSnapshot(payload = {}) {
  if (!desktopCapturer || typeof desktopCapturer.getSources !== "function") {
    throw new Error("desktop_capturer_unavailable");
  }
  const display = resolveCaptureDisplay(payload);
  if (!display) {
    throw new Error("display_not_found");
  }

  const scaleFactor = Number.isFinite(Number(display.scaleFactor)) ? Number(display.scaleFactor) : 1;
  const displayWidth = Math.max(320, Math.floor(Number(display.size?.width || 1280) * scaleFactor));
  const displayHeight = Math.max(240, Math.floor(Number(display.size?.height || 720) * scaleFactor));
  const maxEdge = Math.floor(clampNumber(payload?.max_edge || payload?.maxEdge, 1920, 640, 4096));
  const ratio = Math.min(1, maxEdge / Math.max(displayWidth, displayHeight));
  const thumbWidth = Math.max(320, Math.floor(displayWidth * ratio));
  const thumbHeight = Math.max(240, Math.floor(displayHeight * ratio));

  const sources = await desktopCapturer.getSources({
    types: ["screen"],
    thumbnailSize: { width: thumbWidth, height: thumbHeight },
    fetchWindowIcons: false,
  });
  if (!Array.isArray(sources) || sources.length === 0) {
    throw new Error("screen_source_not_found");
  }

  const targetDisplayId = String(display.id || "").trim();
  let source = sources.find((item) => String(item?.display_id || "").trim() === targetDisplayId);
  if (!source) {
    source = sources[0];
  }
  if (!source || !source.thumbnail || source.thumbnail.isEmpty()) {
    throw new Error("screen_thumbnail_empty");
  }

  const format = String(payload?.format || "jpeg").trim().toLowerCase() === "png" ? "png" : "jpeg";
  const quality = Math.floor(clampNumber(payload?.quality, 78, 35, 95));
  const imageBuffer = format === "png"
    ? source.thumbnail.toPNG()
    : source.thumbnail.toJPEG(quality);
  if (!imageBuffer || !imageBuffer.length) {
    throw new Error("screen_image_empty");
  }
  const mimeType = format === "png" ? "image/png" : "image/jpeg";
  const size = source.thumbnail.getSize();
  const capturedAt = new Date().toISOString();
  const ext = format === "png" ? "png" : "jpg";
  const safeStamp = capturedAt.replace(/[:.]/g, "-");
  return {
    data_url: `data:${mimeType};base64,${imageBuffer.toString("base64")}`,
    name: `screen-${safeStamp}.${ext}`,
    width: Number(size?.width || thumbWidth),
    height: Number(size?.height || thumbHeight),
    source_display: String(source.display_id || targetDisplayId || "unknown"),
    captured_at: capturedAt,
    mime_type: mimeType,
  };
}

function createPetPluginApiApp() {
  const api = express();
  api.disable("x-powered-by");
  api.use(express.json({ limit: "128kb" }));
  api.use(createPluginApiAuthMiddleware());

  api.get("/healthz", (_req, res) => {
    res.json({
      ok: true,
      service: "aelin-pet-plugin-api",
      ts: Date.now(),
    });
  });

  api.get("/v1/pet/state", (_req, res) => {
    res.json({
      ok: true,
      state: buildPetPluginStateSnapshot(true),
      ts: Date.now(),
    });
  });

  api.post("/v1/device/screen/capture", async (req, res) => {
    const body = req.body && typeof req.body === "object" ? req.body : {};
    try {
      const snapshot = await captureScreenSnapshot(body);
      res.json({
        ok: true,
        ...snapshot,
        ts: Date.now(),
      });
    } catch (error) {
      res.status(500).json({
        ok: false,
        detail: error instanceof Error ? error.message : String(error || "screen_capture_failed"),
      });
    }
  });

  api.get("/v1/pet/behavior", (_req, res) => {
    res.json({
      ok: true,
      behavior: getBehaviorRoot(),
      source: petBehaviorLoadedFrom || "default",
      ts: Date.now(),
    });
  });

  api.post("/v1/pet/behavior/reload", (_req, res) => {
    reloadPetBehaviorConfig();
    if (petWindow && !petWindow.isDestroyed()) {
      startPetStateTicker();
    }
    res.json({
      ok: true,
      behavior: getBehaviorRoot(),
      source: petBehaviorLoadedFrom || "default",
      ts: Date.now(),
    });
  });

  api.post("/v1/pet/emotion/override", (req, res) => {
    const result = setPetEmotionOverride(req.body || {});
    if (!result.ok) {
      res.status(400).json(result);
      return;
    }
    res.json({
      ok: true,
      override: result.override,
      state: buildPetPluginStateSnapshot(true),
      ts: Date.now(),
    });
  });

  api.delete("/v1/pet/emotion/override", (_req, res) => {
    const result = clearPetEmotionOverride();
    res.json({
      ok: true,
      changed: Boolean(result.changed),
      state: buildPetPluginStateSnapshot(true),
      ts: Date.now(),
    });
  });

  api.post("/v1/pet/events", (req, res) => {
    const body = req.body && typeof req.body === "object" ? req.body : {};
    const type = String(body.type || "").trim() || "unknown";
    petPluginLastEvent = {
      type,
      payload: body.payload && typeof body.payload === "object" ? body.payload : {},
      ts: Date.now(),
    };
    pushPetState(true);
    res.json({
      ok: true,
      event: petPluginLastEvent,
    });
  });

  api.use((error, _req, res, _next) => {
    res.status(500).json({
      ok: false,
      detail: error instanceof Error ? error.message : String(error || "plugin_api_error"),
    });
  });

  return api;
}

function stopPetPluginApiServer() {
  if (!petPluginApiServer) return;
  try {
    petPluginApiServer.close();
  } catch {
    // ignore close failures
  }
  petPluginApiServer = null;
  petPluginApiPort = 0;
}

function listenPluginApi(port) {
  return new Promise((resolve, reject) => {
    const api = createPetPluginApiApp();
    const server = api.listen(port, "127.0.0.1", () => {
      petPluginApiServer = server;
      const addr = server.address();
      petPluginApiPort = Number(addr && typeof addr === "object" ? addr.port : port) || port;
      petDebugLog("main:plugin-api-started", {
        port: petPluginApiPort,
        tokenRequired: Boolean(PET_PLUGIN_API_TOKEN),
      });
      resolve();
    });
    server.on("error", (error) => {
      reject(error);
    });
  });
}

async function startPetPluginApiServer() {
  if (!PET_PLUGIN_API_ENABLED) return;
  stopPetPluginApiServer();
  const preferredPort = parsePluginApiPort();
  try {
    await listenPluginApi(preferredPort);
  } catch (error) {
    const code = String(error?.code || "");
    if (code === "EADDRINUSE" && preferredPort !== 0) {
      await listenPluginApi(0);
      return;
    }
    throw error;
  }
}

function projectRoot() {
  return path.resolve(__dirname, "..", "..");
}

function backendDir() {
  return app.isPackaged ? path.join(process.resourcesPath, "backend") : path.join(projectRoot(), "backend");
}

function backendRuntimeDir() {
  return path.join(process.resourcesPath, "backend-runtime");
}

function frontendDir() {
  return path.join(projectRoot(), "frontend");
}

function frontendDistDir() {
  return app.isPackaged ? path.join(process.resourcesPath, "frontend-dist") : path.join(frontendDir(), "dist");
}

function normalizeRoute(route) {
  const raw = String(route || "").trim() || "/";
  return raw.startsWith("/") ? raw : `/${raw}`;
}

function buildAppUrl(route = "/") {
  return `http://127.0.0.1:${frontendPort}${normalizeRoute(route)}?desktop=1&compact=1`;
}

function getReferenceDisplayArea() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    const bounds = mainWindow.getBounds();
    const display = screen.getDisplayMatching(bounds);
    if (display?.workArea) return display.workArea;
  }
  return screen.getPrimaryDisplay()?.workArea || { x: 0, y: 0, width: 1440, height: 900 };
}

function resolveWindowPreset(route = "/") {
  return getWindowPreset(route, getReferenceDisplayArea());
}

function clampWindowSize(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getDefaultMainZoom() {
  if (!Number.isFinite(desktopZoom)) return 1.0;
  return Math.max(0.72, Math.min(1.15, desktopZoom));
}

function getMainZoomFactor() {
  if (!mainWindow || mainWindow.isDestroyed()) return getDefaultMainZoom();
  return Number(mainWindow.webContents.getZoomFactor() || getDefaultMainZoom());
}

function setMainZoomFactor(factor) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const clamped = Math.max(MAIN_ZOOM_MIN, Math.min(MAIN_ZOOM_MAX, Number(factor || 1)));
  mainWindow.webContents.setZoomFactor(clamped);
}

function adjustMainZoom(delta) {
  const current = getMainZoomFactor();
  setMainZoomFactor(current + delta);
}

function isMainWindowAtMinimumSize() {
  if (!mainWindow || mainWindow.isDestroyed()) return false;
  const [width, height] = mainWindow.getSize();
  const [minWidth, minHeight] = mainWindow.getMinimumSize();
  return width <= minWidth + 1 && height <= minHeight + 1;
}

function getMainWindowTopLevel() {
  return "screen-saver";
}

function getPetWindowTopLevel() {
  return "screen-saver";
}

function syncWindowZOrder() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindowPinned) {
      mainWindow.setAlwaysOnTop(true, getMainWindowTopLevel());
      if (typeof mainWindow.moveTop === "function") {
        mainWindow.moveTop();
      }
    } else {
      mainWindow.setAlwaysOnTop(false, "normal");
    }
  }
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.setAlwaysOnTop(true, getPetWindowTopLevel());
    if (!mainWindowPinned && typeof petWindow.moveTop === "function") {
      petWindow.moveTop();
    }
  }
}

function setMainWindowPinned(pinned) {
  mainWindowPinned = Boolean(pinned);
  syncWindowZOrder();
}

function toggleMainWindowPinned() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    openModule("/");
    return;
  }
  if (!mainWindowPinned && !isMainWindowAtMinimumSize()) {
    dialog.showMessageBox({
      type: "info",
      title: "窗口置顶",
      message: "请先将主窗口缩小到最小尺寸，再开启置顶。",
      buttons: ["知道了"],
    }).catch(() => {});
    return;
  }
  setMainWindowPinned(!mainWindowPinned);
  syncPetMenu();
}

function isZoomInKey(input) {
  const key = String(input?.key || "").toLowerCase();
  const code = String(input?.code || "");
  return key === "+" || key === "=" || key === "plus" || code === "NumpadAdd" || key === "add";
}

function isZoomOutKey(input) {
  const key = String(input?.key || "").toLowerCase();
  const code = String(input?.code || "");
  return key === "-" || key === "_" || key === "subtract" || code === "NumpadSubtract";
}

function isZoomResetKey(input) {
  const key = String(input?.key || "").toLowerCase();
  const code = String(input?.code || "");
  return key === "0" || code === "Digit0" || code === "Numpad0";
}

function bindMainZoomShortcuts() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.on("before-input-event", (event, input) => {
    if (!input || input.type !== "keyDown") return;
    const hasAccel = process.platform === "darwin" ? Boolean(input.meta) : Boolean(input.control);
    if (!hasAccel) return;
    if (isZoomInKey(input)) {
      event.preventDefault();
      adjustMainZoom(MAIN_ZOOM_STEP);
      return;
    }
    if (isZoomOutKey(input)) {
      event.preventDefault();
      adjustMainZoom(-MAIN_ZOOM_STEP);
      return;
    }
    if (isZoomResetKey(input)) {
      event.preventDefault();
      setMainZoomFactor(getDefaultMainZoom());
    }
  });
}

function applyMainWindowPreset(route = "/") {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const preset = resolveWindowPreset(route);
  mainWindow.setMinimumSize(preset.minWidth, preset.minHeight);
  mainWindow.setMaximumSize(preset.maxWidth, preset.maxHeight);
  const [currentW, currentH] = mainWindow.getSize();
  const nextW = clampWindowSize(currentW, preset.minWidth, preset.maxWidth);
  const nextH = clampWindowSize(currentH, preset.minHeight, preset.maxHeight);
  if (currentW !== nextW || currentH !== nextH) {
    mainWindow.setSize(nextW, nextH);
  }
  mainWindow.setResizable(true);
  mainWindow.setMaximizable(true);
  mainWindow.setFullScreenable(false);
  if (mainWindowPinned && !isMainWindowAtMinimumSize()) {
    setMainWindowPinned(false);
  }
}

function resolveTrayIconPath() {
  const candidates = app.isPackaged
    ? [
      path.join(process.resourcesPath, "frontend-dist", "aelin-icon.ico"),
      path.join(process.resourcesPath, "build", "icon.ico"),
      path.join(process.resourcesPath, "icon.ico"),
    ]
    : [
      path.join(projectRoot(), "desktop", "build", "icon.ico"),
      path.join(projectRoot(), "frontend", "public", "aelin-icon.ico"),
    ];
  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate)) return candidate;
    } catch {
      // ignore path check failures
    }
  }
  return process.execPath;
}

function resolvePetGifDir() {
  const candidates = app.isPackaged
    ? [
      path.join(app.getAppPath(), "gif"),
      path.join(process.resourcesPath, "gif"),
      path.join(process.resourcesPath, "app.asar.unpacked", "gif"),
    ]
    : [
      path.join(projectRoot(), "desktop", "gif"),
      path.join(__dirname, "..", "gif"),
    ];
  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) {
        return candidate;
      }
    } catch {
      // ignore path check failures
    }
  }
  return "";
}

function listPetGifFiles() {
  const dir = resolvePetGifDir();
  if (!dir) return [];
  try {
    return fs
      .readdirSync(dir)
      .filter((name) => /\.gif$/i.test(name))
      .sort((a, b) => a.localeCompare(b, "en"))
      .map((name) => path.join(dir, name));
  } catch {
    return [];
  }
}

function pickGifByHints(files, hints, fallbackIndex) {
  for (const file of files) {
    const base = path.basename(file).toLowerCase();
    if (hints.some((hint) => base.includes(hint))) {
      return file;
    }
  }
  if (!files.length) return "";
  const idx = Math.max(0, Math.min(files.length - 1, fallbackIndex));
  return files[idx];
}

function buildPetStateAssets() {
  const files = listPetGifFiles();
  const resolved = {
    happy: pickGifByHints(files, ["happy", "action_02"], 0),
    completed: pickGifByHints(files, ["completed", "done", "finish", "action_03"], 1),
    resting: pickGifByHints(files, ["resting", "rest", "sleep", "action_04"], 2),
    working: pickGifByHints(files, ["working", "busy", "focus", "action_05"], 3),
  };
  return Object.fromEntries(
    Object.entries(resolved)
      .filter(([, filePath]) => !!filePath)
      .map(([key, filePath]) => [key, pathToFileURL(filePath).href])
  );
}

function buildPetConfigPayload() {
  return {
    icon: `http://127.0.0.1:${frontendPort}/aelin-icon.ico`,
    stateAssets: petStateAssets,
    clickThroughEnabled: petClickThroughEnabled,
    visible: petVisible,
    state: petLastState,
    compactSize: PET_COMPACT_WINDOW_SIZE,
    expandedWidth: PET_EXPANDED_WINDOW_WIDTH,
    expandedMaxHeight: PET_EXPANDED_WINDOW_MAX_HEIGHT,
    layout: { ...petLayoutState },
  };
}

function syncPetMenu() {
  if (!tray) return;
  tray.setContextMenu(createPetMenu());
}

function pushPetConfig() {
  if (!petWindow || petWindow.isDestroyed()) return;
  petWindow.webContents.send("pet:config", buildPetConfigPayload());
}

function sampleSystemCpuUsage() {
  let cores = [];
  try {
    cores = os.cpus() || [];
  } catch {
    cores = [];
  }
  if (!Array.isArray(cores) || !cores.length) return 0;
  let idle = 0;
  let total = 0;
  for (const core of cores) {
    const times = core && core.times ? core.times : {};
    const user = Number(times.user || 0);
    const nice = Number(times.nice || 0);
    const sys = Number(times.sys || 0);
    const irq = Number(times.irq || 0);
    const idlePart = Number(times.idle || 0);
    idle += idlePart;
    total += user + nice + sys + irq + idlePart;
  }
  const now = { idle, total };
  if (!petCpuSnapshot) {
    petCpuSnapshot = now;
    return 0;
  }
  const idleDelta = now.idle - petCpuSnapshot.idle;
  const totalDelta = now.total - petCpuSnapshot.total;
  petCpuSnapshot = now;
  if (totalDelta <= 0) return 0;
  const usage = 1 - idleDelta / totalDelta;
  return Math.max(0, Math.min(1, usage));
}

function normalizeProcessName(rawName) {
  const cleaned = String(rawName || "")
    .trim()
    .toLowerCase()
    .replace(/^"+|"+$/g, "")
    .replace(/\\/g, "/");
  if (!cleaned) return "";
  const base = cleaned.split("/").pop() || cleaned;
  return base.replace(/\.exe$/i, "");
}

function parseProcessNamesFromText(text) {
  const lines = String(text || "")
    .split(/\r?\n/g)
    .map((line) => normalizeProcessName(line))
    .filter(Boolean);
  return new Set(lines);
}

function runCommandAsync(command, args, timeoutMs = getProbeCommandTimeoutMs()) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (error, output) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (error) {
        reject(error);
      } else {
        resolve(String(output || "").trim());
      }
    };

    child.stdout?.on("data", (chunk) => {
      stdout += String(chunk || "");
    });
    child.stderr?.on("data", (chunk) => {
      stderr += String(chunk || "");
    });

    child.on("error", (error) => {
      finish(error instanceof Error ? error : new Error(String(error || "command error")));
    });

    child.on("close", (code) => {
      if (Number(code || 0) === 0) {
        finish(null, stdout);
        return;
      }
      const detail = String(stderr || stdout || "").trim() || `${command} exit ${code}`;
      finish(new Error(detail));
    });

    const timer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        // ignore timeout kill failures
      }
      finish(new Error(`timeout:${command}`));
    }, Math.max(1000, Number(timeoutMs || getProbeCommandTimeoutMs())));
  });
}

function runPowerShellScriptAsync(script, timeoutMs = getProbeCommandTimeoutMs()) {
  const wrapped = `$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $OutputEncoding=[Console]::OutputEncoding; ${String(script || "")}`;
  return runCommandAsync(
    "powershell",
    ["-NoProfile", "-Command", wrapped],
    timeoutMs
  );
}

async function collectWindowsProcessNamesAsync() {
  const cmd = "$ErrorActionPreference='Stop'; Get-Process | Select-Object -ExpandProperty ProcessName | ConvertTo-Json -Compress";
  const raw = await runPowerShellScriptAsync(cmd, getProbeCommandTimeoutMs());
  if (!raw) return new Set();
  let parsed = [];
  try {
    const json = JSON.parse(raw);
    parsed = Array.isArray(json) ? json : [json];
  } catch {
    return parseProcessNamesFromText(raw);
  }
  const names = parsed.map((item) => normalizeProcessName(item)).filter(Boolean);
  return new Set(names);
}

async function collectPosixProcessNamesAsync() {
  const raw = await runCommandAsync("ps", ["-A", "-o", "comm="], getProbeCommandTimeoutMs());
  return parseProcessNamesFromText(raw || "");
}

async function collectSystemProcessNamesAsync() {
  if (process.platform === "win32") return collectWindowsProcessNamesAsync();
  return collectPosixProcessNamesAsync();
}

function matchProcessTokens(processNames, tokens) {
  const tokenSet = new Set(
    Array.isArray(tokens)
      ? tokens.map((item) => normalizeProcessToken(item)).filter(Boolean)
      : []
  );
  if (!tokenSet.size) return [];
  const matches = [];
  for (const procName of processNames) {
    const normalized = normalizeProcessToken(procName);
    if (!normalized) continue;
    if (tokenSet.has(normalized)) {
      matches.push(normalized);
    }
  }
  return Array.from(new Set(matches));
}

function schedulePetProcessProbe(force = false) {
  const nowTs = Date.now();
  if (petProcessProbeCache.inFlight) return;
  if (!force && nowTs - Number(petProcessProbeCache.ts || 0) < getProcessProbeCacheMs()) return;

  petProcessProbeCache.inFlight = true;
  collectSystemProcessNamesAsync()
    .then((names) => {
      petProcessProbeCache.ts = Date.now();
      petProcessProbeCache.names = names;
      petProcessProbeCache.error = "";
    })
    .catch((error) => {
      petProcessProbeCache.ts = Date.now();
      petProcessProbeCache.error = error instanceof Error ? error.message : String(error || "process probe error");
    })
    .finally(() => {
      petProcessProbeCache.inFlight = false;
      pushPetState(false);
    });
}

function collectPetProcessRuntime() {
  schedulePetProcessProbe(false);
  const names = petProcessProbeCache.names instanceof Set ? petProcessProbeCache.names : new Set();
  return {
    ok: !petProcessProbeCache.error || names.size > 0,
    names,
    workMatches: matchProcessTokens(names, WORK_PROCESS_TOKENS),
    musicMatches: matchProcessTokens(names, MUSIC_PROCESS_TOKENS),
    error: petProcessProbeCache.error,
  };
}

function runPowerShellScript(script) {
  const wrapped = `$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $OutputEncoding=[Console]::OutputEncoding; ${String(script || "")}`;
  const probe = spawnSync("powershell", ["-NoProfile", "-Command", wrapped], {
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    encoding: "utf8",
  });
  if (probe.error) {
    throw new Error(probe.error.message || String(probe.error));
  }
  if (probe.status !== 0) {
    throw new Error(String(probe.stderr || probe.stdout || "").trim() || `powershell exit ${probe.status}`);
  }
  return String(probe.stdout || "").trim();
}

function parseJsonSafely(raw, fallback = {}) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch {
    const objectStart = text.indexOf("{");
    const objectEnd = text.lastIndexOf("}");
    if (objectStart >= 0 && objectEnd > objectStart) {
      try {
        return JSON.parse(text.slice(objectStart, objectEnd + 1));
      } catch {
        // ignore
      }
    }
    const arrayStart = text.indexOf("[");
    const arrayEnd = text.lastIndexOf("]");
    if (arrayStart >= 0 && arrayEnd > arrayStart) {
      try {
        return JSON.parse(text.slice(arrayStart, arrayEnd + 1));
      } catch {
        // ignore
      }
    }
    return fallback;
  }
}

function resolveDesktopScriptPath(scriptName) {
  const fileName = String(scriptName || "").trim();
  if (!fileName) return "";
  const scriptPath = path.join(__dirname, "scripts", fileName);
  try {
    if (fs.existsSync(scriptPath)) return scriptPath;
  } catch {
    // ignore script path check failures
  }
  return "";
}

function runPowerShellFileAsync(scriptPath, args = [], timeoutMs = getProbeCommandTimeoutMs()) {
  if (!scriptPath) {
    return Promise.reject(new Error("missing_script_path"));
  }
  const psArgs = [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    scriptPath,
    ...(Array.isArray(args) ? args.map((item) => String(item || "")) : []),
  ];
  return runCommandAsync("powershell", psArgs, timeoutMs);
}

async function collectWindowsMediaSessionsAsync() {
  const scriptPath = resolveDesktopScriptPath("media_sessions.ps1");
  const preferred = MUSIC_PROCESS_TOKENS.join(",");
  const raw = await runPowerShellFileAsync(
    scriptPath,
    ["-Preferred", preferred],
    getProbeCommandTimeoutMs()
  );
  const parsed = parseJsonSafely(raw, { ok: false, reason: "invalid_json", sessions: [] });
  const sessionsRaw = Array.isArray(parsed.sessions)
    ? parsed.sessions
    : parsed.sessions && typeof parsed.sessions === "object"
      ? [parsed.sessions]
      : [];
  const sessions = sessionsRaw.map((item) => ({
    ok: true,
    reason: "",
    title: String(item?.title || "").trim(),
    artist: String(item?.artist || "").trim(),
    album: String(item?.album || "").trim(),
    status: String(item?.status || "").trim(),
    app: String(item?.app || "").trim(),
    canPlay: Boolean(item?.canPlay),
    canPause: Boolean(item?.canPause),
    canNext: Boolean(item?.canNext),
    canPrev: Boolean(item?.canPrev),
    isPreferred: Boolean(item?.isPreferred),
    coverBase64: String(item?.coverBase64 || "").trim(),
  }));
  return {
    ok: Boolean(parsed.ok),
    reason: String(parsed.reason || ""),
    sessions,
  };
}

function parseTrackInfoFromWindowTitle(rawTitle) {
  const title = String(rawTitle || "").trim();
  if (!title) return { title: "", artist: "" };
  const normalized = title
    .replace(/\s+/g, " ")
    .replace(/\s*[|｜]\s*(qq音乐|qqmusic|spotify|网易云音乐|cloudmusic|酷狗音乐|kugou|酷我音乐|kwmusic)\s*$/i, "")
    .replace(/\s*-\s*(qq音乐|qqmusic|spotify|网易云音乐|cloudmusic|酷狗音乐|kugou|酷我音乐|kwmusic)\s*$/i, "")
    .trim();
  if (!normalized) return { title: "", artist: "" };
  const chunks = normalized.split(/\s*[-–—]\s*/).filter(Boolean);
  if (chunks.length >= 2) {
    return {
      title: chunks[0].trim(),
      artist: chunks.slice(1).join(" - ").trim(),
    };
  }
  return { title: normalized, artist: "" };
}

async function collectWindowsMusicWindowTitlesAsync(processTokens) {
  const tokens = Array.isArray(processTokens)
    ? processTokens.map((item) => normalizeProcessToken(item)).filter(Boolean)
    : [];
  if (!tokens.length) return [];
  const escaped = tokens.map((token) => `'${token.replace(/'/g, "''")}'`).join(",");
  const script = [
    "$ErrorActionPreference='Stop'",
    `$targets=@(${escaped})`,
    "$items=Get-Process | Where-Object { $_.MainWindowTitle -and $targets -contains ($_.ProcessName.ToLower()) } | Select-Object ProcessName,MainWindowTitle | ConvertTo-Json -Compress",
    "if([string]::IsNullOrWhiteSpace($items)){ '[]'; exit 0 }",
    "$items",
  ].join("; ");
  const raw = await runPowerShellScriptAsync(script, getProbeCommandTimeoutMs());
  const parsed = parseJsonSafely(raw, []);
  const rows = Array.isArray(parsed) ? parsed : parsed && typeof parsed === "object" ? [parsed] : [];
  return rows
    .map((item) => ({
      processName: normalizeProcessToken(item?.ProcessName || item?.processName),
      windowTitle: String(item?.MainWindowTitle || item?.windowTitle || "").trim(),
    }))
    .filter((item) => item.processName && item.windowTitle);
}

async function enrichMediaByWindowTitleAsync(runtime, preferredProcesses) {
  const base = runtime && typeof runtime === "object" ? runtime : buildEmptyMediaRuntime("no_media");
  if ((base.title && base.artist) || !Array.isArray(preferredProcesses) || !preferredProcesses.length) {
    return base;
  }
  try {
    const rows = await collectWindowsMusicWindowTitlesAsync(preferredProcesses);
    if (!rows.length) return base;
    const chosen = rows.find((row) => preferredProcesses.includes(row.processName)) || rows[0];
    const parsed = parseTrackInfoFromWindowTitle(chosen.windowTitle);
    return {
      ...base,
      title: base.title || parsed.title || `${displayProcessName(chosen.processName)} 正在运行`,
      artist: base.artist || parsed.artist || "",
      app: base.app || displayProcessName(chosen.processName),
      available: true,
      error: "",
    };
  } catch {
    return base;
  }
}

function scoreMediaSession(session, preferredHints = []) {
  const status = String(session?.status || "").toLowerCase();
  const app = String(session?.app || "").toLowerCase();
  let score = 0;
  if (status.includes("playing")) score += 120;
  if (session?.title || session?.artist) score += 80;
  if (session?.canPlay || session?.canPause || session?.canNext || session?.canPrev) score += 40;
  if (session?.isPreferred) score += 90;
  if (app) {
    if (preferredHints.some((hint) => app.includes(hint))) score += 70;
    if (MUSIC_PROCESS_TOKENS.some((hint) => app.includes(hint))) score += 30;
  }
  if (session?.title && String(session.title).trim().length >= 2) score += 20;
  return score;
}

function selectBestMediaSession(sessions, preferredProcesses = []) {
  const list = Array.isArray(sessions) ? sessions : [];
  if (!list.length) return null;
  const preferredHints = preferredProcesses
    .map((item) => normalizeProcessToken(item))
    .filter(Boolean);
  let best = null;
  let bestScore = -Infinity;
  for (const session of list) {
    const score = scoreMediaSession(session, preferredHints);
    if (score > bestScore) {
      bestScore = score;
      best = session;
    }
  }
  return best;
}

function normalizeCoverMime(mime) {
  const raw = String(mime || "").trim().toLowerCase();
  if (!raw) return "image/jpeg";
  const allowed = new Set([
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/gif",
  ]);
  if (allowed.has(raw)) {
    return raw === "image/jpg" ? "image/jpeg" : raw;
  }
  if (raw.startsWith("image/")) return raw;
  return "image/jpeg";
}

function mapMediaSnapshotToRuntime(snapshot, selectedSession) {
  const target = selectedSession || null;
  if (!target) {
    return buildEmptyMediaRuntime(snapshot?.reason || "no_session");
  }
  const status = String(target.status || "").toLowerCase();
  const coverBase64 = String(target.coverBase64 || "").trim();
  const coverMime = normalizeCoverMime(target.coverMime);
  return {
    available: Boolean(target.ok !== false),
    title: target.title,
    artist: target.artist,
    status: target.status || "unknown",
    app: target.app,
    isPlaying: status.includes("playing"),
    canPlay: target.canPlay,
    canPause: target.canPause,
    canNext: target.canNext,
    canPrev: target.canPrev,
    volume: petVolumeEstimate,
    coverDataUrl: coverBase64 ? `data:${coverMime};base64,${coverBase64}` : "",
    error: "",
  };
}

function buildEmptyMediaRuntime(errorText = "") {
  return {
    available: false,
    title: "",
    artist: "",
    status: "unknown",
    app: "",
    isPlaying: false,
    canPlay: false,
    canPause: false,
    canNext: false,
    canPrev: false,
    volume: petVolumeEstimate,
    coverDataUrl: "",
    error: String(errorText || ""),
  };
}

function schedulePetMediaProbe(force = false, preferredProcesses = []) {
  const nowTs = Date.now();
  if (petMediaCache.inFlight) return;
  if (!force && nowTs - Number(petMediaCache.ts || 0) < getMediaProbeCacheMs()) return;
  const preferred = Array.isArray(preferredProcesses)
    ? preferredProcesses.map((item) => normalizeProcessToken(item)).filter(Boolean)
    : [];
  const previous = petMediaCache.snapshot && typeof petMediaCache.snapshot === "object" ? petMediaCache.snapshot : null;
  const shouldKeepProbing = preferred.length > 0
    || Boolean(previous?.isPlaying)
    || Boolean(String(previous?.title || "").trim())
    || Boolean(String(previous?.artist || "").trim());
  if (!force && !shouldKeepProbing) return;

  if (process.platform !== "win32") {
    petMediaCache.ts = nowTs;
    petMediaCache.snapshot = buildEmptyMediaRuntime("unsupported_platform");
    petMediaCache.error = "unsupported_platform";
    return;
  }

  petMediaCache.inFlight = true;
  collectWindowsMediaSessionsAsync()
    .then(async (snapshot) => {
      const selected = selectBestMediaSession(snapshot.sessions || [], preferred);
      let data = mapMediaSnapshotToRuntime(snapshot, selected);
      data = await enrichMediaByWindowTitleAsync(data, preferred);
      petMediaCache.ts = Date.now();
      petMediaCache.snapshot = data;
      petMediaCache.error = data.error || "";
    })
    .catch((error) => {
      const err = error instanceof Error ? error.message : String(error || "media probe error");
      petMediaCache.ts = Date.now();
      petMediaCache.snapshot = previous
        ? {
            ...previous,
            error: err,
          }
        : buildEmptyMediaRuntime(err);
      petMediaCache.error = err;
    })
    .finally(() => {
      petMediaCache.inFlight = false;
      pushPetState(false);
    });
}

function collectPetMediaRuntime(force = false, preferredProcesses = []) {
  const preferred = Array.isArray(preferredProcesses)
    ? preferredProcesses.map((item) => normalizeProcessToken(item)).filter(Boolean)
    : [];
  const cached = petMediaCache.snapshot && typeof petMediaCache.snapshot === "object" ? petMediaCache.snapshot : null;
  const needsPreferredRefresh = preferred.length > 0
    && (!cached || (!String(cached.title || "").trim() && !String(cached.artist || "").trim()));
  schedulePetMediaProbe(force || needsPreferredRefresh, preferred);
  if (petMediaCache.snapshot) return petMediaCache.snapshot;
  if (process.platform !== "win32") return buildEmptyMediaRuntime("unsupported_platform");
  return buildEmptyMediaRuntime("");
}

function invokeWindowsMediaControl(action) {
  if (process.platform !== "win32") {
    return { ok: false, detail: "unsupported_platform" };
  }
  const actionNorm = String(action || "").trim().toLowerCase();
  if (!["play", "pause", "play_pause", "next", "previous"].includes(actionNorm)) {
    return { ok: false, detail: "invalid_action" };
  }
  const scriptPath = resolveDesktopScriptPath("media_control.ps1");
  if (!scriptPath) return { ok: false, detail: "missing_script" };
  try {
    const raw = runPowerShellScript(`& '${scriptPath.replace(/'/g, "''")}' -Action '${actionNorm}'`);
    const parsed = parseJsonSafely(raw, { ok: false });
    return { ok: Boolean(parsed.ok), detail: String(parsed.reason || "") };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error || "media_control_error");
    return { ok: false, detail };
  }
}

function invokeSystemVolumeControl(action, value) {
  if (process.platform !== "win32") {
    return { ok: false, detail: "unsupported_platform", volume: null };
  }
  const actionNorm = String(action || "").trim().toLowerCase();
  if (!["get", "set", "up", "down"].includes(actionNorm)) {
    return { ok: false, detail: "invalid_volume_action", volume: null };
  }
  const scriptPath = resolveDesktopScriptPath("system_volume.ps1");
  if (!scriptPath) return { ok: false, detail: "missing_script", volume: null };
  try {
    const cmdParts = [`& '${scriptPath.replace(/'/g, "''")}'`, `-Action '${actionNorm}'`];
    if (Number.isFinite(Number(value))) {
      cmdParts.push(`-Value ${Number(value)}`);
    }
    const raw = runPowerShellScript(cmdParts.join(" "));
    const parsed = parseJsonSafely(raw, { ok: false, reason: "parse_error", volume: null });
    const volumeNum = Number(parsed.volume);
    return {
      ok: Boolean(parsed.ok),
      detail: String(parsed.reason || ""),
      volume: Number.isFinite(volumeNum) ? Math.max(0, Math.min(100, Math.round(volumeNum))) : null,
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error || "system_volume_error");
    return { ok: false, detail, volume: null };
  }
}

function sendWindowsMediaTransportKey(action) {
  if (process.platform !== "win32") return false;
  const actionNorm = String(action || "").trim().toLowerCase();
  const keyMap = {
    play: "MEDIA_PLAY_PAUSE",
    pause: "MEDIA_PLAY_PAUSE",
    play_pause: "MEDIA_PLAY_PAUSE",
    next: "MEDIA_NEXT_TRACK",
    previous: "MEDIA_PREV_TRACK",
  };
  const keyName = keyMap[actionNorm];
  if (!keyName) return false;
  const script = `$ws=New-Object -ComObject WScript.Shell; $ws.SendKeys('{${keyName}}')`;
  try {
    runPowerShellScript(script);
    return true;
  } catch {
    return false;
  }
}

function sendWindowsVolumeKeys(kind, steps = 1) {
  if (process.platform !== "win32") return false;
  const keyName = String(kind || "").toUpperCase() === "DOWN" ? "VOLUME_DOWN" : "VOLUME_UP";
  const count = Math.max(1, Math.min(50, Number(steps || 1)));
  const script = `$ws=New-Object -ComObject WScript.Shell; 1..${count} | ForEach-Object { $ws.SendKeys('{${keyName}}') }`;
  try {
    runPowerShellScript(script);
    return true;
  } catch {
    return false;
  }
}

function controlSystemVolume(action, value) {
  const syncCacheVolume = (nextVolume) => {
    if (Number.isFinite(Number(nextVolume))) {
      petVolumeEstimate = Math.max(0, Math.min(100, Math.round(Number(nextVolume))));
    }
    if (petMediaCache.snapshot && typeof petMediaCache.snapshot === "object") {
      petMediaCache.snapshot.volume = petVolumeEstimate;
    }
  };
  const actionNorm = String(action || "").trim().toLowerCase();
  const applyRealVolumeResult = (result) => {
    if (result?.ok && Number.isFinite(Number(result.volume))) {
      syncCacheVolume(result.volume);
    }
    return {
      ok: Boolean(result?.ok),
      detail: String(result?.detail || ""),
      volume: petVolumeEstimate,
    };
  };

  if (actionNorm === "get_volume") {
    const result = invokeSystemVolumeControl("get");
    if (!result.ok) return { ok: false, detail: result.detail || "volume_get_failed", volume: petVolumeEstimate };
    return applyRealVolumeResult(result);
  }

  if (actionNorm === "volume_up") {
    const result = invokeSystemVolumeControl("up");
    if (result.ok) return applyRealVolumeResult(result);
    const ok = sendWindowsVolumeKeys("UP", 3);
    if (!ok) return { ok: false, detail: result.detail || "volume_up_failed", volume: petVolumeEstimate };
    syncCacheVolume(petVolumeEstimate + 6);
    return { ok: true, detail: "fallback_sendkeys", volume: petVolumeEstimate };
  }
  if (actionNorm === "volume_down") {
    const result = invokeSystemVolumeControl("down");
    if (result.ok) return applyRealVolumeResult(result);
    const ok = sendWindowsVolumeKeys("DOWN", 3);
    if (!ok) return { ok: false, detail: result.detail || "volume_down_failed", volume: petVolumeEstimate };
    syncCacheVolume(petVolumeEstimate - 6);
    return { ok: true, detail: "fallback_sendkeys", volume: petVolumeEstimate };
  }
  if (actionNorm === "set_volume") {
    const target = Math.max(0, Math.min(100, Number(value || 0)));
    const result = invokeSystemVolumeControl("set", target);
    if (result.ok) return applyRealVolumeResult(result);
    const diff = target - petVolumeEstimate;
    if (Math.abs(diff) < 2) return { ok: true, detail: "skip_small_diff", volume: petVolumeEstimate };
    const steps = Math.max(1, Math.round(Math.abs(diff) / 2));
    const ok = sendWindowsVolumeKeys(diff > 0 ? "UP" : "DOWN", steps);
    if (!ok) return { ok: false, detail: result.detail || "set_volume_failed", volume: petVolumeEstimate };
    syncCacheVolume(target);
    return { ok: true, detail: "fallback_sendkeys", volume: petVolumeEstimate };
  }
  return { ok: false, detail: "unsupported_volume_action", volume: petVolumeEstimate };
}

function sanitizeCoachLine(rawText) {
  return String(rawText || "")
    .replace(/\[(?:expression|表情)\s*:[^\]]+\]/gi, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 48);
}

function fallbackCoachLine(reason) {
  if (reason === "late_night") {
    return "夜深了呢主人，记得早点休息，我会一直陪着你。";
  }
  return "又专注了很久呢主人，先活动一下肩颈再继续吧。";
}

async function readMainWindowAuthToken() {
  if (!mainWindow || mainWindow.isDestroyed()) return "";
  try {
    const token = await mainWindow.webContents.executeJavaScript("localStorage.getItem('token') || ''", true);
    return String(token || "").trim();
  } catch {
    return "";
  }
}

function postJsonWithTimeout(url, payload, headers = {}, timeoutMs = 25000) {
  return new Promise((resolve, reject) => {
    let urlObj;
    try {
      urlObj = new URL(url);
    } catch (error) {
      reject(error);
      return;
    }
    const body = JSON.stringify(payload || {});
    const req = http.request({
      protocol: urlObj.protocol,
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: `${urlObj.pathname}${urlObj.search}`,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
        ...headers,
      },
    }, (res) => {
      let data = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        data += chunk;
      });
      res.on("end", () => {
        const code = Number(res.statusCode || 0);
        const parsed = parseJsonSafely(data, {});
        if (code >= 200 && code < 300) {
          resolve(parsed);
          return;
        }
        reject(new Error(String(parsed.detail || res.statusMessage || `http_${code}`)));
      });
    });
    req.on("error", (error) => reject(error));
    req.setTimeout(Math.max(1000, timeoutMs), () => {
      req.destroy(new Error("timeout"));
    });
    req.write(body);
    req.end();
  });
}

async function requestCoachLineFromAgent(reason, context) {
  const token = await readMainWindowAuthToken();
  if (!token) throw new Error("missing_token");
  const reasonText = reason === "late_night" ? "夜深提示" : "长时专注提醒";
  const workNames = (context.workDisplayNames || []).join("、") || "无";
  const query = [
    "你是桌宠 Aelin。",
    `场景：${reasonText}。`,
    `当前工作进程：${workNames}。`,
    `专注时长：${Math.max(0, Number(context.workDurationMin || 0))} 分钟。`,
    "请只输出一句中文提醒，称呼“主人”，12-28字，温柔自然，不要分点，不要解释，不要附加标签。",
  ].join("");
  const response = await postJsonWithTimeout(
    `http://127.0.0.1:${backendPort}/api/v1/aelin/chat`,
    {
      query,
      use_memory: false,
      max_citations: 0,
      workspace: "desktop_pet",
      history: [],
    },
    {
      Authorization: `Bearer ${token}`,
    },
    30000
  );
  const line = sanitizeCoachLine(response?.answer || "");
  if (!line) throw new Error("empty_line");
  return line;
}

function maybeTriggerCoachLine(context) {
  const nowTs = Number(context.nowTs || Date.now());
  if (petCoachPending) return;
  if (nowTs < petCoachCooldownUntil) return;

  let reason = "";
  if (context.isWorking && Number(context.workDurationMin || 0) >= getCoachLongFocusTriggerMin()) {
    reason = "long_focus";
  } else if (context.isLateNight) {
    const stamp = nowLocalDateStamp(nowTs);
    if (petLateNightHintDate !== stamp) {
      reason = "late_night";
      petLateNightHintDate = stamp;
    }
  }
  if (!reason) return;

  petCoachPending = true;
  petCoachCooldownUntil = nowTs + getCoachCooldownMs();

  (async () => {
    try {
      const line = await requestCoachLineFromAgent(reason, context);
      petCoachLine = line;
      petCoachReason = reason;
    } catch {
      petCoachLine = fallbackCoachLine(reason);
      petCoachReason = `${reason}:fallback`;
    } finally {
      petCoachLineUntil = Date.now() + getCoachVisibleMs();
      petCoachPending = false;
      pushPetState(true);
    }
  })();
}

function handlePetMediaControl(action, payload) {
  const act = String(action || "").trim().toLowerCase();
  if (!act) return { ok: false, detail: "missing_action" };

  if (act === "volume_up" || act === "volume_down" || act === "set_volume") {
    const result = controlSystemVolume(act, payload?.value);
    petMediaCache.ts = 0;
    schedulePetMediaProbe(true);
    return result;
  }

  if (act === "play" || act === "pause" || act === "play_pause" || act === "next" || act === "previous") {
    let result = invokeWindowsMediaControl(act);
    if (!result.ok) {
      const fallbackOk = sendWindowsMediaTransportKey(act);
      if (fallbackOk) {
        result = { ok: true, detail: "fallback_media_key" };
      }
    }
    petMediaCache.ts = 0;
    schedulePetMediaProbe(true);
    return result;
  }

  return { ok: false, detail: "unsupported_action" };
}

function getMainRoute() {
  if (!mainWindow || mainWindow.isDestroyed()) return "/";
  const raw = String(mainWindow.webContents.getURL() || "");
  if (!raw) return "/";
  try {
    return normalizeRoute(new URL(raw).pathname || "/");
  } catch {
    return "/";
  }
}

function computePetRuntimeState() {
  let idleSec = 0;
  let idleState = "active";
  try {
    idleSec = Math.max(0, Number(powerMonitor.getSystemIdleTime() || 0));
    idleState = String(powerMonitor.getSystemIdleState(60) || "active").toLowerCase();
  } catch {
    idleSec = 0;
    idleState = "active";
  }
  const cpuUsage = sampleSystemCpuUsage();
  const route = getMainRoute();
  const nowTs = Date.now();
  const processRuntime = collectPetProcessRuntime();
  const workMatches = processRuntime.workMatches || [];
  const musicMatches = processRuntime.musicMatches || [];
  const mediaRuntime = collectPetMediaRuntime(false, musicMatches);
  const isWorking = workMatches.length > 0;
  const hasMusic = Boolean(mediaRuntime.isPlaying) || musicMatches.length > 0;
  const workDisplayNames = uniqueDisplayNames(workMatches, 3);
  const musicDisplayNames = uniqueDisplayNames(musicMatches, 2);
  let state = "happy";
  if (isWorking) {
    if (!petWorkingPhase || !petWorkStartedAt) {
      petWorkStartedAt = nowTs;
    }
    petWorkingPhase = true;
    petCompletionUntil = 0;
    state = "working";
  } else {
    if (petWorkingPhase) {
      petWorkingPhase = false;
      petCompletionUntil = nowTs + getStateCompletionHoldMs();
    }
    if (nowTs < petCompletionUntil) {
      state = "completed";
    } else {
      petWorkStartedAt = 0;
      state = hasMusic ? "happy" : "resting";
    }
  }

  const workDurationMin = petWorkStartedAt ? Math.max(0, Math.floor((nowTs - petWorkStartedAt) / 60000)) : 0;
  const hour = new Date(nowTs).getHours();
  const isLateNight = isWithinLateNightWindow(hour);

  maybeTriggerCoachLine({
    nowTs,
    isWorking,
    isLateNight,
    workDurationMin,
    workDisplayNames,
  });

  if (petCoachLine && nowTs > petCoachLineUntil) {
    petCoachLine = "";
    petCoachReason = "";
  }

  const emotion = computePetEmotion(
    {
      isWorking,
      workDurationMin,
      idleSec,
      cpuUsage,
      isLateNight,
      hasMusic,
      isMusicPlaying: Boolean(mediaRuntime.isPlaying),
    },
    getBehaviorRoot(),
    getActivePetEmotionOverride(nowTs)
  );

  const workNarration = buildWorkNarration(workMatches, workDisplayNames, workDurationMin);

  petLastState = state;
  return {
    state,
    idleSec,
    idleState,
    cpuUsage: Number(cpuUsage.toFixed(3)),
    route,
    processProbeOk: Boolean(processRuntime.ok),
    processProbeError: processRuntime.error || "",
    workMatches,
    workDisplayNames,
    workDurationMin,
    musicMatches,
    musicDisplayNames,
    hasMusic,
    media: mediaRuntime,
    workNarration,
    emotion,
    coachLine: petCoachLine || "",
    coachReason: petCoachReason || "",
    isLateNight,
    ts: nowTs,
  };
}

function pushPetState(force = false) {
  if (!petWindow || petWindow.isDestroyed()) return;
  const payload = computePetRuntimeState();
  petLastRuntimeState = payload;
  const mediaKey = `${String(payload.media?.title || "")}|${String(payload.media?.artist || "")}|${payload.media?.isPlaying ? "1" : "0"}|${Number(payload.media?.volume || 0)}`;
  const workKey = Array.isArray(payload.workMatches) ? payload.workMatches.join(",") : "";
  const coachKey = String(payload.coachLine || "");
  const emotion = payload.emotion && typeof payload.emotion === "object" ? payload.emotion : {};
  const emotionKey = [
    String(emotion.mood || ""),
    Number(emotion.valence || 0),
    Number(emotion.energy || 0),
    Number(emotion.focus || 0),
    Number(emotion.tension || 0),
    String(emotion.source || ""),
  ].join("|");
  const idleBucket = payload.state === "resting" ? Math.floor(Number(payload.idleSec || 0) / 15) : 0;
  const workDurationBucket = Math.floor(Math.max(0, Number(payload.workDurationMin || 0)));
  const key = `${payload.state}|${idleBucket}|${payload.route}|${workKey}|${workDurationBucket}|${mediaKey}|${coachKey}|${emotionKey}`;
  if (!force && key === petStateLastKey) return;
  petStateLastKey = key;
  petWindow.webContents.send("pet:state", payload);
}

function stopPetHoverGuard() {
  if (petHoverGuardTimer) {
    clearInterval(petHoverGuardTimer);
    petHoverGuardTimer = null;
  }
  petHoverGuardOutsideCount = 0;
}

function runPetHoverGuardTick() {
  if (!petWindow || petWindow.isDestroyed()) {
    petHoverGuardOutsideCount = 0;
    return;
  }
  if (!petWindow.isVisible()) {
    petHoverGuardOutsideCount = 0;
    return;
  }
  if (petDragState) {
    petHoverGuardOutsideCount = 0;
    return;
  }
  if (String(petLayoutState.mode || "compact") !== "expanded") {
    petHoverGuardOutsideCount = 0;
    return;
  }

  const cursor = screen.getCursorScreenPoint();
  const bounds = petWindow.getBounds();
  const margin = getHoverGuardMarginPx();
  const inside = (
    Number(cursor.x || 0) >= Number(bounds.x || 0) - margin
    && Number(cursor.x || 0) <= Number(bounds.x || 0) + Number(bounds.width || 0) + margin
    && Number(cursor.y || 0) >= Number(bounds.y || 0) - margin
    && Number(cursor.y || 0) <= Number(bounds.y || 0) + Number(bounds.height || 0) + margin
  );
  if (inside) {
    petHoverGuardOutsideCount = 0;
    return;
  }

  petHoverGuardOutsideCount += 1;
  if (petHoverGuardOutsideCount < getHoverGuardOutsideTicks()) return;
  petHoverGuardOutsideCount = 0;
  petDebugLog("main:hover-guard-collapse", {
    cursor: {
      x: Number(cursor.x || 0),
      y: Number(cursor.y || 0),
    },
    bounds: {
      x: Number(bounds.x || 0),
      y: Number(bounds.y || 0),
      width: Number(bounds.width || 0),
      height: Number(bounds.height || 0),
    },
    clickThroughEnabled: petClickThroughEnabled,
    pointerActive: petPointerActive,
  });
  try {
    if (petClickThroughEnabled) {
      petPointerActive = false;
      applyPetMouseMode();
    }
    petWindow.webContents.send("pet:force-collapse", {
      reason: "main_guard_pointer_outside",
      ts: Date.now(),
    });
  } catch {
    // ignore renderer sync failures
  }
}

function startPetHoverGuard() {
  stopPetHoverGuard();
  petHoverGuardTimer = setInterval(() => {
    runPetHoverGuardTick();
  }, getHoverGuardIntervalMs());
}

function stopPetStateTicker() {
  if (petStateTimer) {
    clearInterval(petStateTimer);
    petStateTimer = null;
  }
  stopPetHoverGuard();
}

function startPetStateTicker() {
  stopPetStateTicker();
  petCpuSnapshot = null;
  sampleSystemCpuUsage();
  controlSystemVolume("get_volume");
  schedulePetProcessProbe(true);
  schedulePetMediaProbe(true);
  petStateTimer = setInterval(() => {
    pushPetState(false);
  }, getStatePushIntervalMs());
  startPetHoverGuard();
  pushPetState(true);
}

function bindPetPowerEvents() {
  if (petPowerEventsBound) return;
  petPowerEventsBound = true;
  const events = [
    "lock-screen",
    "unlock-screen",
    "suspend",
    "resume",
    "user-did-become-active",
    "user-did-resign-active",
  ];
  for (const eventName of events) {
    try {
      powerMonitor.on(eventName, () => {
        setTimeout(() => pushPetState(true), 120);
      });
    } catch {
      // ignore unsupported power events
    }
  }
}

function sqliteUrl(absPath) {
  return `sqlite:///${String(absPath || "").replace(/\\/g, "/")}`;
}

function requestOk(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      const code = Number(res.statusCode || 0);
      res.resume();
      resolve(code >= 200 && code < 500);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(2500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForUrl(url, timeoutMs = 45000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    // eslint-disable-next-line no-await-in-loop
    if (await requestOk(url)) return true;
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

function killProcTree(proc) {
  if (!proc || proc.killed) return;
  if (process.platform === "win32") {
    const killer = spawn("taskkill", ["/pid", String(proc.pid), "/t", "/f"], { windowsHide: true });
    killer.on("error", () => {
      try {
        proc.kill("SIGTERM");
      } catch {
        // ignore kill errors
      }
    });
    return;
  }
  try {
    proc.kill("SIGTERM");
  } catch {
    // ignore kill errors
  }
}

function spawnViaCmd(commandLine, options) {
  const comspec = process.env.COMSPEC || "cmd.exe";
  const normalized = process.platform === "win32" ? `chcp 65001>nul && ${commandLine}` : commandLine;
  return spawn(comspec, ["/d", "/s", "/c", normalized], options);
}

function sanitizePythonPath(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  const match = trimmed.match(/^"(.*)"$/);
  return match ? match[1] : trimmed;
}

function buildPythonCandidates(requestedPython) {
  const items = [];
  const seen = new Set();
  function pushCandidate(command, args = []) {
    const key = `${String(command || "").toLowerCase()}|${args.join(" ")}`;
    if (!command || seen.has(key)) return;
    seen.add(key);
    items.push({ command, args, label: [command, ...args].join(" ") });
  }

  const requested = sanitizePythonPath(requestedPython);
  if (requested) pushCandidate(requested, []);

  // Prefer plain `python` to avoid broken `py -3` mappings on Windows.
  pushCandidate("python", []);

  if (process.platform === "win32") {
    pushCandidate("py", ["-3.12"]);
    pushCandidate("py", ["-3.11"]);
    pushCandidate("py", ["-3.10"]);
    pushCandidate("py", ["-3"]);
  }

  return items;
}

function probePythonRunner(candidate, cwd, env) {
  try {
    const probe = spawnSync(
      candidate.command,
      [...candidate.args, "-c", "import sys,uvicorn;print(sys.executable)"],
      {
        cwd,
        env,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        encoding: "utf8",
      }
    );

    if (probe.error) {
      return { ok: false, reason: probe.error.message || String(probe.error) };
    }
    if (probe.status !== 0) {
      const reason = String(probe.stderr || probe.stdout || "").trim();
      return { ok: false, reason: reason || `exit code ${probe.status}` };
    }
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: error instanceof Error ? error.message : String(error) };
  }
}

function stripAnsiCodes(text) {
  return String(text || "").replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "");
}

function normalizeLogText(text, tag) {
  let s = stripAnsiCodes(text).replace(/\uFFFD/g, "");
  s = s.replace(/[\u279C\u27A4\u25B8\u203A\u2192]/g, ">");
  // Some Windows terminals decode the leading glyph into mojibake before "Local:".
  if (tag === "frontend") {
    s = s.replace(/^[^\r\nA-Za-z0-9\u4e00-\u9fff]*Local:/gm, "Local:");
    s = s.replace(/^[^\r\nA-Za-z0-9\u4e00-\u9fff]*Network:/gm, "Network:");
  }
  return s;
}

function pipeTaggedLog(proc, tag) {
  if (!proc) return;
  const outDecoder = new StringDecoder("utf8");
  const errDecoder = new StringDecoder("utf8");
  proc.stdout.on("data", (chunk) => {
    const text = normalizeLogText(outDecoder.write(Buffer.from(chunk)), tag);
    if (text) process.stdout.write(`[${tag}] ${text}`);
  });
  proc.stderr.on("data", (chunk) => {
    const text = normalizeLogText(errDecoder.write(Buffer.from(chunk)), tag);
    if (text) process.stderr.write(`[${tag}] ${text}`);
  });
}

function startBackend() {
  const userData = app.getPath("userData");
  const mediaDir = path.join(userData, "media");
  fs.mkdirSync(mediaDir, { recursive: true });
  const dbFile = path.join(userData, "mercurydesk.db");

  const env = {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    MERCURYDESK_DATABASE_URL: sqliteUrl(dbFile),
    MERCURYDESK_MEDIA_DIR: mediaDir,
    MERCURYDESK_CORS_ORIGINS: [
      `http://127.0.0.1:${frontendPort}`,
      `http://localhost:${frontendPort}`,
      "http://127.0.0.1:5173",
      "http://localhost:5173",
    ].join(","),
    MERCURYDESK_BROWSER_TOOL_HEADLESS: process.env.MERCURYDESK_BROWSER_TOOL_HEADLESS || "0",
    MERCURYDESK_BROWSER_TOOL_OPEN_EXTERNAL_ON_NAVIGATE:
      process.env.MERCURYDESK_BROWSER_TOOL_OPEN_EXTERNAL_ON_NAVIGATE || "1",
    MERCURYDESK_BROWSER_TOOL_MODE_DEFAULT: process.env.MERCURYDESK_BROWSER_TOOL_MODE_DEFAULT || "auto",
    MERCURYDESK_BROWSER_TOOL_CDP_ENABLED: process.env.MERCURYDESK_BROWSER_TOOL_CDP_ENABLED || "1",
    MERCURYDESK_BROWSER_TOOL_CDP_ENDPOINT:
      process.env.MERCURYDESK_BROWSER_TOOL_CDP_ENDPOINT || "http://127.0.0.1:9222",
  };
  const pluginBaseUrl = petPluginApiPort > 0 ? `http://127.0.0.1:${petPluginApiPort}` : "";
  if (pluginBaseUrl) {
    env.MERCURYDESK_DESKTOP_PLUGIN_BASE_URL = pluginBaseUrl;
  }
  if (PET_PLUGIN_API_TOKEN) {
    env.MERCURYDESK_DESKTOP_PLUGIN_TOKEN = PET_PLUGIN_API_TOKEN;
  }

  if (app.isPackaged) {
    const runtimeRoot = backendRuntimeDir();
    const exeName = process.platform === "win32" ? "aelin-backend.exe" : "aelin-backend";
    const exePath = path.join(runtimeRoot, exeName);
    if (!fs.existsSync(exePath)) {
      throw new Error(`Bundled backend unavailable: ${exePath}`);
    }
    backendProc = spawn(exePath, [], {
      cwd: runtimeRoot,
      env,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    pipeTaggedLog(backendProc, "backend");
    backendProc.on("error", (err) => {
      if (closing) return;
      dialog.showErrorBox("Backend startup failed", String(err?.message || err));
    });
    return;
  }

  const root = backendDir();
  if (!fs.existsSync(root)) {
    throw new Error(`Backend directory missing: ${root}`);
  }

  const requestedPython = String(process.env.MERCURYDESK_PYTHON || "");
  const pythonCandidates = buildPythonCandidates(requestedPython);
  const failed = [];

  for (const candidate of pythonCandidates) {
    const probe = probePythonRunner(candidate, root, env);
    if (!probe.ok) {
      failed.push(`${candidate.label}: ${probe.reason}`);
      continue;
    }
    safeConsoleLog(`[backend] Python runner selected: ${candidate.label}`);
    backendProc = spawn(
      candidate.command,
      [...candidate.args, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)],
      {
        cwd: root,
        env,
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
    break;
  }

  if (!backendProc) {
    const details = failed.length ? `\nCandidate probe failed:\n- ${failed.join("\n- ")}` : "";
    throw new Error(`Unable to start backend Python process.${details}`);
  }

  pipeTaggedLog(backendProc, "backend");
  backendProc.on("error", (err) => {
    if (closing) return;
    dialog.showErrorBox("Backend startup failed", String(err?.message || err));
  });
}

function startFrontendDev() {
  if (process.env.MERCURYDESK_DESKTOP_SKIP_FRONTEND_DEV === "1") return;
  const cmd = `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`;
  frontendDevProc = spawnViaCmd(cmd, {
    cwd: frontendDir(),
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      BROWSER: "none",
      FORCE_COLOR: "0",
      NO_COLOR: "1",
      npm_config_color: "false",
    },
  });
  pipeTaggedLog(frontendDevProc, "frontend");
}

function startFrontendServer() {
  const dist = frontendDistDir();
  if (!fs.existsSync(dist)) {
    throw new Error(`Frontend dist missing: ${dist}. Please run frontend build first.`);
  }

  const web = express();
  // Express strips the mount prefix (/api, /media) before handing to proxy.
  // So target must include the same prefix to avoid forwarding /v1/... by mistake.
  web.use("/api", createProxyMiddleware({ target: `http://127.0.0.1:${backendPort}/api`, changeOrigin: true }));
  web.use("/media", createProxyMiddleware({ target: `http://127.0.0.1:${backendPort}/media`, changeOrigin: true }));
  web.use(express.static(dist));
  web.get("*", (_req, res) => {
    res.sendFile(path.join(dist, "index.html"));
  });

  frontendServer = web.listen(frontendPort, "127.0.0.1");
}

function createMainWindow(initialRoute = "/", showWhenReady = false) {
  const preset = resolveWindowPreset(initialRoute);
  mainWindow = new BrowserWindow({
    width: preset.width,
    height: preset.height,
    minWidth: preset.minWidth,
    minHeight: preset.minHeight,
    maxWidth: preset.maxWidth,
    maxHeight: preset.maxHeight,
    resizable: true,
    maximizable: true,
    fullscreenable: false,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#111111",
    title: "Aelin",
    icon: resolveTrayIconPath(),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  setMainZoomFactor(getDefaultMainZoom());
  bindMainZoomShortcuts();

  mainWindow.loadURL(buildAppUrl(initialRoute));
  mainWindow.once("ready-to-show", () => {
    if (showWhenReady) {
      mainWindow.show();
    }
  });
  mainWindow.on("resize", () => {
    if (mainWindowPinned && !isMainWindowAtMinimumSize()) {
      setMainWindowPinned(false);
    }
    syncPetMenu();
  });
  mainWindow.on("minimize", () => {
    if (closing) return;
    setTimeout(() => ensurePetVisible(), 30);
  });
  mainWindow.on("hide", () => {
    if (closing) return;
    setTimeout(() => ensurePetVisible(), 30);
  });
  mainWindow.on("closed", () => {
    mainWindowPinned = false;
    mainWindow = null;
    if (!closing) {
      setTimeout(() => ensurePetVisible(), 30);
    }
  });
}

function openModule(route = "/") {
  const targetUrl = buildAppUrl(route);
  if (!mainWindow) {
    createMainWindow(route, true);
    return;
  }
  applyMainWindowPreset(route);
  const maybePromise = mainWindow.loadURL(targetUrl);
  if (maybePromise && typeof maybePromise.catch === "function") {
    maybePromise.catch(() => {});
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.show();
  mainWindow.focus();
  syncWindowZOrder();
  pushPetState(true);
}

function createPetMenu() {
  const pinEntry = (isMainWindowAtMinimumSize() || mainWindowPinned)
    ? [{ label: mainWindowPinned ? "取消主窗口置顶" : "主窗口置顶", click: () => toggleMainWindowPinned() }]
    : [];
  return Menu.buildFromTemplate([
    { label: "Chat", click: () => openModule("/") },
    { label: "Settings", click: () => openModule("/settings") },
    { label: "Processes", click: () => openModule("/processes") },
    { label: "Tracking", click: () => openModule("/tracking") },
    { label: "Diary", click: () => openModule("/diary") },
    ...pinEntry,
    { type: "separator" },
    { label: petVisible ? "收起桌宠" : "显示桌宠", click: () => setPetVisible(!petVisible) },
    { label: petClickThroughEnabled ? "关闭点击穿透" : "开启点击穿透", click: () => setPetClickThroughEnabled(!petClickThroughEnabled) },
    { type: "separator" },
    { label: "Focus", click: () => openModule("/focus") },
    { type: "separator" },
    { label: "退出 Aelin", click: () => app.quit() },
  ]);
}
function popupPetMenu(options = {}) {
  if (!petWindow || petWindow.isDestroyed()) return;
  const menu = createPetMenu();
  const bounds = petWindow.getBounds();
  const localX = Number(options?.x);
  const localY = Number(options?.y);
  const screenX = Number(options?.screenX);
  const screenY = Number(options?.screenY);
  const cursor = screen.getCursorScreenPoint();
  const resolvedLocalX = Number.isFinite(localX)
    ? localX
    : Number.isFinite(screenX)
      ? screenX - bounds.x
      : cursor.x - bounds.x;
  const resolvedLocalY = Number.isFinite(localY)
    ? localY
    : Number.isFinite(screenY)
      ? screenY - bounds.y
      : cursor.y - bounds.y;
  menu.popup({
    window: petWindow,
    x: Math.max(0, Math.floor(resolvedLocalX)),
    y: Math.max(0, Math.floor(resolvedLocalY)),
    callback: () => {
      if (!petWindow || petWindow.isDestroyed()) return;
      syncWindowZOrder();
      if (mainWindowPinned && mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.show();
        mainWindow.focus();
      } else {
        petWindow.focus();
      }
    },
  });
}

function popupPetMenuAtCursor() {
  popupPetMenu();
}

function ensurePetVisible() {
  petVisible = true;
  if (!petWindow || petWindow.isDestroyed()) {
    createPetWindow();
    syncPetMenu();
    return;
  }
  if (petWindow.isMinimized()) {
    petWindow.restore();
  }
  if (!petWindow.isVisible()) {
    petWindow.showInactive();
  }
  syncWindowZOrder();
  syncPetMenu();
  pushPetConfig();
  pushPetState(true);
}

function setPetVisible(visible) {
  const next = !!visible;
  if (petVisible === next) return;
  petVisible = next;
  if (!petWindow || petWindow.isDestroyed()) {
    if (next) {
      createPetWindow();
    }
    syncPetMenu();
    return;
  }
  if (next) {
    ensurePetVisible();
  } else {
    petWindow.hide();
    syncPetMenu();
    pushPetConfig();
  }
}

function applyPetMouseMode() {
  if (!petWindow || petWindow.isDestroyed()) return;
  if (!petClickThroughEnabled) {
    petWindow.setIgnoreMouseEvents(false, { forward: false });
    return;
  }
  petWindow.setIgnoreMouseEvents(!petPointerActive, { forward: !petPointerActive });
}

function setPetClickThroughEnabled(enabled) {
  const next = !!enabled;
  if (petClickThroughEnabled === next) return;
  petClickThroughEnabled = next;
  if (!petClickThroughEnabled) {
    petPointerActive = true;
  }
  applyPetMouseMode();
  syncPetMenu();
  pushPetConfig();
}

function setPetPointerActive(active) {
  if (!petWindow || petWindow.isDestroyed()) return;
  const next = !!active;
  if (petPointerActive === next && petClickThroughEnabled) return;
  const prev = petPointerActive;
  petPointerActive = next;
  petDebugLog("main:pointer-active", {
    prev,
    next,
    clickThroughEnabled: petClickThroughEnabled,
    hasDragState: Boolean(petDragState),
  });
  applyPetMouseMode();
  if (!next) {
    petDragState = null;
    stopPetDragLoop();
  }
}

function payloadToDipPoint(payload) {
  const rawX = Number(payload?.screenX);
  const rawY = Number(payload?.screenY);
  if (!Number.isFinite(rawX) || !Number.isFinite(rawY)) return null;
  return { x: Math.round(rawX), y: Math.round(rawY) };
}

function getCursorDipPoint() {
  const point = screen.getCursorScreenPoint();
  return {
    x: Number(point?.x || 0),
    y: Number(point?.y || 0),
  };
}

function isFinitePoint(point) {
  return !!point && Number.isFinite(point.x) && Number.isFinite(point.y);
}

function clampNumber(value, min, max, fallback) {
  const raw = Number(value);
  const safe = Number.isFinite(raw) ? raw : Number(fallback);
  const lower = Number(min);
  const upper = Number(max);
  return Math.max(lower, Math.min(upper, safe));
}

function normalizePetLayoutPayload(payload) {
  const mode = String(payload?.mode || "compact").toLowerCase() === "expanded" ? "expanded" : "compact";
  const width = mode === "expanded"
    ? Math.round(clampNumber(payload?.width, PET_COMPACT_WINDOW_SIZE, PET_EXPANDED_WINDOW_WIDTH, PET_EXPANDED_WINDOW_WIDTH))
    : PET_COMPACT_WINDOW_SIZE;
  const height = mode === "expanded"
    ? Math.round(clampNumber(payload?.height, PET_COMPACT_WINDOW_SIZE, PET_EXPANDED_WINDOW_MAX_HEIGHT, 300))
    : PET_COMPACT_WINDOW_SIZE;
  const anchorX = clampNumber(payload?.anchorX, 0, width, width / 2);
  const anchorY = clampNumber(payload?.anchorY, 0, height, mode === "expanded" ? Math.min(height - 16, height * 0.62) : height / 2);
  return {
    mode,
    width,
    height,
    anchorX,
    anchorY,
  };
}

function resolveCurrentPetAnchor(bounds) {
  const safeBounds = bounds || { width: PET_COMPACT_WINDOW_SIZE, height: PET_COMPACT_WINDOW_SIZE };
  return {
    x: clampNumber(
      petLayoutState.anchorX,
      0,
      Number(safeBounds.width || PET_COMPACT_WINDOW_SIZE),
      Number(safeBounds.width || PET_COMPACT_WINDOW_SIZE) / 2
    ),
    y: clampNumber(
      petLayoutState.anchorY,
      0,
      Number(safeBounds.height || PET_COMPACT_WINDOW_SIZE),
      Number(safeBounds.height || PET_COMPACT_WINDOW_SIZE) / 2
    ),
  };
}

function clampBoundsToArea(x, y, width, height, area) {
  const minX = Number(area?.x || 0);
  const minY = Number(area?.y || 0);
  const maxX = minX + Number(area?.width || width) - Number(width || 0);
  const maxY = minY + Number(area?.height || height) - Number(height || 0);
  return {
    x: Math.max(minX, Math.min(maxX, Math.round(x))),
    y: Math.max(minY, Math.min(maxY, Math.round(y))),
  };
}

function applyPetWindowLayout(payload) {
  if (!petWindow || petWindow.isDestroyed()) return null;
  const currentBounds = petWindow.getBounds();
  const normalized = normalizePetLayoutPayload(payload);
  const currentAnchor = resolveCurrentPetAnchor(currentBounds);
  const screenAnchorX = Number(currentBounds.x || 0) + Number(currentAnchor.x || 0);
  const screenAnchorY = Number(currentBounds.y || 0) + Number(currentAnchor.y || 0);

  let nextX = screenAnchorX - normalized.anchorX;
  let nextY = screenAnchorY - normalized.anchorY;
  const display = screen.getDisplayNearestPoint({
    x: Math.round(screenAnchorX),
    y: Math.round(screenAnchorY),
  });
  const area = display?.workArea || display?.bounds || screen.getPrimaryDisplay()?.workArea || { x: 0, y: 0, width: 1280, height: 720 };
  const clamped = clampBoundsToArea(nextX, nextY, normalized.width, normalized.height, area);
  nextX = clamped.x;
  nextY = clamped.y;

  try {
    petWindow.setBounds({
      x: Math.round(nextX),
      y: Math.round(nextY),
      width: Math.round(normalized.width),
      height: Math.round(normalized.height),
    }, false);
  } catch {
    return null;
  }

  const changed = (
    Math.abs(Number(currentBounds.x || 0) - Math.round(nextX)) > 0
    || Math.abs(Number(currentBounds.y || 0) - Math.round(nextY)) > 0
    || Math.abs(Number(currentBounds.width || 0) - Math.round(normalized.width)) > 0
    || Math.abs(Number(currentBounds.height || 0) - Math.round(normalized.height)) > 0
    || String(petLayoutState.mode || "compact") !== String(normalized.mode || "compact")
  );
  if (changed) {
    petDebugLog("main:layout-apply", {
      mode: normalized.mode,
      from: {
        x: Number(currentBounds.x || 0),
        y: Number(currentBounds.y || 0),
        width: Number(currentBounds.width || 0),
        height: Number(currentBounds.height || 0),
        anchorX: Number(currentAnchor.x || 0),
        anchorY: Number(currentAnchor.y || 0),
      },
      to: {
        x: Math.round(nextX),
        y: Math.round(nextY),
        width: Math.round(normalized.width),
        height: Math.round(normalized.height),
        anchorX: Math.round(normalized.anchorX),
        anchorY: Math.round(normalized.anchorY),
      },
    });
  }

  petLayoutState = {
    mode: normalized.mode,
    width: normalized.width,
    height: normalized.height,
    anchorX: normalized.anchorX,
    anchorY: normalized.anchorY,
  };
  return petWindow.getBounds();
}

function ensurePetWindowCompactBounds() {
  if (!petWindow || petWindow.isDestroyed()) return null;
  const bounds = petWindow.getBounds();
  const target = PET_COMPACT_WINDOW_SIZE;
  const invalidSize = Math.abs(Number(bounds.width || 0) - target) > 2
    || Math.abs(Number(bounds.height || 0) - target) > 2
    || petLayoutState.mode !== "compact";
  if (!invalidSize) return bounds;
  const compact = applyPetWindowLayout({
    mode: "compact",
    width: target,
    height: target,
    anchorX: target / 2,
    anchorY: target / 2,
  });
  return compact || petWindow.getBounds();
}

function chooseDragAnchor(payload, bounds) {
  const payloadPoint = payloadToDipPoint(payload);
  const cursorPoint = getCursorDipPoint();
  const localX = Number(payload?.localX);
  const localY = Number(payload?.localY);
  const targetX = Number.isFinite(localX)
    ? Math.max(0, Math.min(Number(bounds.width || 0), Math.round(localX)))
    : Math.round(Number(bounds.width || 0) / 2);
  const targetY = Number.isFinite(localY)
    ? Math.max(0, Math.min(Number(bounds.height || 0), Math.round(localY)))
    : Math.round(Number(bounds.height || 0) / 2);
  const width = Number(bounds.width || PET_COMPACT_WINDOW_SIZE);
  const height = Number(bounds.height || PET_COMPACT_WINDOW_SIZE);
  const rawAnchorX = isFinitePoint(cursorPoint) ? Number(cursorPoint.x || 0) - Number(bounds.x || 0) : NaN;
  const rawAnchorY = isFinitePoint(cursorPoint) ? Number(cursorPoint.y || 0) - Number(bounds.y || 0) : NaN;
  const localInRangeX = Number.isFinite(localX) && localX >= 0 && localX <= width;
  const localInRangeY = Number.isFinite(localY) && localY >= 0 && localY <= height;
  const anchorXRaw = Number.isFinite(rawAnchorX)
    ? rawAnchorX
    : localInRangeX
      ? localX
      : targetX;
  const anchorYRaw = Number.isFinite(rawAnchorY)
    ? rawAnchorY
    : localInRangeY
      ? localY
      : targetY;
  const anchorX = Math.max(0, Math.min(width, Number(anchorXRaw || 0)));
  const anchorY = Math.max(0, Math.min(height, Number(anchorYRaw || 0)));

  const pointer = isFinitePoint(cursorPoint)
    ? cursorPoint
    : isFinitePoint(payloadPoint)
      ? payloadPoint
      : { x: Number(bounds.x || 0) + anchorX, y: Number(bounds.y || 0) + anchorY };
  const source = isFinitePoint(cursorPoint) ? "cursor" : isFinitePoint(payloadPoint) ? "payload" : "fallback";

  return {
    source,
    multiplier: 1,
    pointer: {
      x: Math.round(pointer.x),
      y: Math.round(pointer.y),
    },
    anchorX: Math.round(anchorX),
    anchorY: Math.round(anchorY),
    scaleFactor: 1,
    targetX,
    targetY,
  };
}

function resolveDragPointer(payload, dragState) {
  const payloadPoint = payloadToDipPoint(payload);
  const cursorPoint = getCursorDipPoint();
  if (isFinitePoint(cursorPoint)) {
    return {
      x: cursorPoint.x,
      y: cursorPoint.y,
    };
  }
  if (isFinitePoint(payloadPoint)) {
    return { x: payloadPoint.x, y: payloadPoint.y };
  }
  if (petWindow && !petWindow.isDestroyed()) {
    const bounds = petWindow.getBounds();
    return {
      x: Number(bounds.x || 0) + Number(dragState?.anchorX || 0),
      y: Number(bounds.y || 0) + Number(dragState?.anchorY || 0),
    };
  }
  return {
    x: Number(dragState?.startX || 0),
    y: Number(dragState?.startY || 0),
  };
}

function stopPetDragLoop() {
  if (!petDragTimer) return;
  clearInterval(petDragTimer);
  petDragTimer = null;
}

function startPetDragLoop() {
  stopPetDragLoop();
  petDragTimer = setInterval(() => {
    updatePetDragPosition(null);
  }, 16);
}

function clampPetWindowPosition(nextX, nextY, pointer) {
  if (!petWindow || petWindow.isDestroyed()) {
    return { x: Math.round(nextX), y: Math.round(nextY) };
  }
  const basePoint = isFinitePoint(pointer) ? pointer : getCursorDipPoint();
  const display = screen.getDisplayNearestPoint({
    x: Math.round(Number(basePoint?.x || 0)),
    y: Math.round(Number(basePoint?.y || 0)),
  });
  const area = display?.workArea || display?.bounds;
  if (!area) {
    return { x: Math.round(nextX), y: Math.round(nextY) };
  }
  const bounds = petWindow.getBounds();
  const minX = Number(area.x || 0);
  const minY = Number(area.y || 0);
  const maxX = minX + Number(area.width || 0) - Number(bounds.width || PET_COMPACT_WINDOW_SIZE);
  const maxY = minY + Number(area.height || 0) - Number(bounds.height || PET_COMPACT_WINDOW_SIZE);
  return {
    x: Math.max(minX, Math.min(maxX, Math.round(nextX))),
    y: Math.max(minY, Math.min(maxY, Math.round(nextY))),
  };
}

function updatePetDragPosition(payload) {
  if (!petWindow || petWindow.isDestroyed() || !petDragState) return;
  const pointer = resolveDragPointer(payload, petDragState);
  const anchorX = Number(petDragState.anchorX || 0);
  const anchorY = Number(petDragState.anchorY || 0);
  const unclampedX = Number(pointer.x || 0) - anchorX;
  const unclampedY = Number(pointer.y || 0) - anchorY;
  const clamped = clampPetWindowPosition(unclampedX, unclampedY, pointer);
  const nextX = clamped.x;
  const nextY = clamped.y;
  const current = petWindow.getBounds();
  const diffX = nextX - current.x;
  const diffY = nextY - current.y;
  const changed = Math.abs(diffX) > 1 || Math.abs(diffY) > 1;
  if (changed) {
    petWindow.setPosition(nextX, nextY);
  }
  petDragState.moveCount = Number(petDragState.moveCount || 0) + 1;
}

function setupPetIpcHandlers() {
  if (petIpcHandlersRegistered) return;
  petIpcHandlersRegistered = true;

  const fromPet = (event) => {
    return !!petWindow && !petWindow.isDestroyed() && event.sender === petWindow.webContents;
  };

  ipcMain.on("pet:open-chat", (event) => {
    if (!fromPet(event)) return;
    openModule("/");
  });

  ipcMain.on("pet:set-pointer-active", (event, payload) => {
    if (!fromPet(event)) return;
    setPetPointerActive(Boolean(payload?.active));
  });

  ipcMain.on("pet:debug-log", (event, payload) => {
    if (!fromPet(event) || !PET_DEBUG_LOG_ENABLED) return;
    const tag = String(payload?.tag || "renderer:event");
    const seq = Number(payload?.seq || 0);
    const ts = Number(payload?.ts || 0);
    const data = payload?.data && typeof payload.data === "object" ? payload.data : {};
    petDebugLog(tag, {
      seq,
      ts,
      ...data,
    });
  });

  ipcMain.on("pet:open-menu", (event, payload) => {
    if (!fromPet(event)) return;
    popupPetMenu({
      screenX: Number(payload?.screenX),
      screenY: Number(payload?.screenY),
    });
  });

  ipcMain.on("pet:drag-start", (event, payload) => {
    if (!fromPet(event) || !petWindow || petWindow.isDestroyed()) return;
    setPetPointerActive(true);
    const bounds = petWindow.getBounds();
    const anchor = chooseDragAnchor(payload, bounds);
    petDragState = {
      source: anchor.source,
      multiplier: anchor.multiplier,
      scaleFactor: anchor.scaleFactor,
      anchorX: anchor.anchorX,
      anchorY: anchor.anchorY,
      startX: anchor.pointer.x,
      startY: anchor.pointer.y,
      moveCount: 0,
    };
    updatePetDragPosition(payload);
    startPetDragLoop();
  });

  ipcMain.on("pet:drag-move", (event, payload) => {
    if (!fromPet(event) || !petWindow || petWindow.isDestroyed() || !petDragState) return;
    updatePetDragPosition(payload);
  });

  ipcMain.on("pet:drag-end", (event) => {
    if (!fromPet(event)) return;
    petDragState = null;
    stopPetDragLoop();
  });

  ipcMain.on("pet:set-layout", (event, payload) => {
    if (!fromPet(event) || !petWindow || petWindow.isDestroyed()) return;
    const appliedBounds = applyPetWindowLayout(payload || {});
    if (!petWindow.isVisible()) return;
    syncWindowZOrder();
    return appliedBounds;
  });

  ipcMain.on("pet:apply-layout-sync", (event, payload) => {
    if (!fromPet(event) || !petWindow || petWindow.isDestroyed()) {
      event.returnValue = { ok: false, applied: null };
      return;
    }
    const applied = applyPetWindowLayout(payload || {});
    if (petWindow.isVisible()) {
      syncWindowZOrder();
    }
    event.returnValue = {
      ok: true,
      applied: applied
        ? {
            x: Number(applied.x || 0),
            y: Number(applied.y || 0),
            width: Number(applied.width || 0),
            height: Number(applied.height || 0),
          }
        : null,
    };
  });

  ipcMain.handle("pet:apply-layout", (event, payload) => {
    if (!fromPet(event) || !petWindow || petWindow.isDestroyed()) {
      return { ok: false, applied: null };
    }
    const applied = applyPetWindowLayout(payload || {});
    if (petWindow.isVisible()) {
      syncWindowZOrder();
    }
    return {
      ok: true,
      applied: applied
        ? {
            x: Number(applied.x || 0),
            y: Number(applied.y || 0),
            width: Number(applied.width || 0),
            height: Number(applied.height || 0),
          }
        : null,
    };
  });

  ipcMain.handle("pet:get-config", (event) => {
    if (!fromPet(event)) return {};
    return buildPetConfigPayload();
  });

  ipcMain.handle("pet:media-control", (event, payload) => {
    if (!fromPet(event)) return { ok: false, detail: "forbidden" };
    const action = String(payload?.action || "");
    const result = handlePetMediaControl(action, payload || {});
    const state = computePetRuntimeState();
    petLastRuntimeState = state;
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send("pet:state", state);
    }
    return {
      ok: Boolean(result.ok),
      detail: String(result.detail || ""),
      state,
    };
  });
}

function createTray() {
  if (tray) return;
  try {
    tray = new Tray(resolveTrayIconPath());
  } catch {
    tray = null;
    return;
  }
  tray.setToolTip("Aelin");
  syncPetMenu();
  tray.on("click", () => {
    ensurePetVisible();
  });
  tray.on("double-click", () => {
    ensurePetVisible();
    openModule("/");
  });
}

function createPetWindow() {
  setupPetIpcHandlers();
  if (!Object.keys(petStateAssets).length) {
    petStateAssets = buildPetStateAssets();
  }
  const petSize = PET_COMPACT_WINDOW_SIZE;
  const display = screen.getPrimaryDisplay();
  const area = display?.workArea || { x: 0, y: 0, width: 1280, height: 720 };
  const x = area.x + area.width - petSize - 18;
  const y = area.y + area.height - petSize - 28;

  petWindow = new BrowserWindow({
    width: petSize,
    height: petSize,
    minWidth: PET_COMPACT_WINDOW_SIZE,
    minHeight: PET_COMPACT_WINDOW_SIZE,
    maxWidth: PET_EXPANDED_WINDOW_WIDTH,
    maxHeight: PET_EXPANDED_WINDOW_MAX_HEIGHT,
    x,
    y,
    frame: false,
    transparent: true,
    hasShadow: false,
    resizable: false,
    movable: false,
    focusable: true,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    autoHideMenuBar: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "pet-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  syncWindowZOrder();
  petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  petWindow.setSkipTaskbar(true);
  petWindow.setMenuBarVisibility(false);
  petPointerActive = false;
  petLayoutState = {
    mode: "compact",
    width: petSize,
    height: petSize,
    anchorX: petSize / 2,
    anchorY: petSize / 2,
  };
  applyPetMouseMode();

  petWindow.loadFile(path.join(__dirname, "pet.html"), {
    query: {
      icon: `http://127.0.0.1:${frontendPort}/aelin-icon.ico`,
      debug: PET_DEBUG_LOG_ENABLED ? "1" : "0",
    },
  });
  petWindow.webContents.on("did-finish-load", () => {
    pushPetConfig();
    pushPetState(true);
  });

  let lastMenuTs = 0;
  const tryPopup = (coords = {}) => {
    const now = Date.now();
    if (now - lastMenuTs < 150) return;
    lastMenuTs = now;
    popupPetMenu(coords);
  };

  petWindow.webContents.on("context-menu", (_event, params) => {
    const lx = Number(params?.x);
    const ly = Number(params?.y);
    tryPopup({
      x: Number.isFinite(lx) ? lx : undefined,
      y: Number.isFinite(ly) ? ly : undefined,
    });
  });

  petWindow.webContents.on("before-input-event", (event, input) => {
    if (input.type === "mouseDown" && input.button === "right") {
      event.preventDefault();
      tryPopup({});
    }
  });

  petWindow.on("system-context-menu", (_event, point) => {
    const x = Number(point?.x);
    const y = Number(point?.y);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      tryPopup({ screenX: x, screenY: y });
      return;
    }
    tryPopup();
  });

  if (process.platform === "win32" && typeof petWindow.hookWindowMessage === "function") {
    const WM_RBUTTONDOWN = 0x0204;
    const WM_RBUTTONUP = 0x0205;
    const WM_CONTEXTMENU = 0x007b;
    const WM_NCRBUTTONDOWN = 0x00A4;
    const WM_NCRBUTTONUP = 0x00A5;
    petWindow.hookWindowMessage(WM_RBUTTONDOWN, () => {
      tryPopup();
    });
    petWindow.hookWindowMessage(WM_RBUTTONUP, () => {
      tryPopup();
    });
    petWindow.hookWindowMessage(WM_NCRBUTTONDOWN, () => {
      tryPopup();
    });
    petWindow.hookWindowMessage(WM_NCRBUTTONUP, () => {
      popupPetMenuAtCursor();
    });
    petWindow.hookWindowMessage(WM_CONTEXTMENU, () => {
      popupPetMenuAtCursor();
    });
  }

  petWindow.on("minimize", (event) => {
    event.preventDefault();
    if (!petVisible) return;
    ensurePetVisible();
  });

  petWindow.on("hide", () => {
    if (closing || !petVisible) return;
    setTimeout(() => ensurePetVisible(), 30);
  });

  petWindow.on("blur", () => {
    if (!petWindow || petWindow.isDestroyed()) return;
    syncWindowZOrder();
  });

  petWindow.on("closed", () => {
    petWindow = null;
    petDragState = null;
    stopPetDragLoop();
    stopPetStateTicker();
  });
  startPetStateTicker();
  syncPetMenu();
}

async function boot() {
  reloadPetBehaviorConfig();
  await startPetPluginApiServer();
  startBackend();
  const backendReady = await waitForUrl(`http://127.0.0.1:${backendPort}/healthz`, 60000);
  if (!backendReady) {
    throw new Error(
      app.isPackaged
        ? "Bundled backend startup timed out. Please reinstall or check logs."
        : "Backend startup timed out. Check Python environment and dependencies."
    );
  }

  if (isDev) {
    startFrontendDev();
  } else {
    startFrontendServer();
  }

  const frontendReady = await waitForUrl(`http://127.0.0.1:${frontendPort}`, 60000);
  if (!frontendReady) {
    throw new Error("Frontend startup timed out.");
  }
}

function cleanup() {
  closing = true;
  petDragState = null;
  stopPetDragLoop();
  stopPetStateTicker();
  stopPetPluginApiServer();
  if (tray) {
    try {
      tray.destroy();
    } catch {
      // ignore tray destroy errors
    }
    tray = null;
  }
  if (petWindow && !petWindow.isDestroyed()) {
    try {
      petWindow.close();
    } catch {
      // ignore close errors
    }
    petWindow = null;
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    try {
      mainWindow.close();
    } catch {
      // ignore close errors
    }
    mainWindow = null;
  }
  if (frontendServer) {
    try {
      frontendServer.close();
    } catch {
      // ignore close errors
    }
    frontendServer = null;
  }
  killProcTree(frontendDevProc);
  killProcTree(backendProc);
  frontendDevProc = null;
  backendProc = null;
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    if (!closing) {
      createTray();
      ensurePetVisible();
      return;
    }
    app.quit();
  }
});

app.on("before-quit", () => {
  cleanup();
});

app.whenReady().then(async () => {
  try {
    await boot();
    petStateAssets = buildPetStateAssets();
    bindPetPowerEvents();
    createMainWindow("/", false);
    createPetWindow();
    createTray();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    dialog.showErrorBox("Aelin Desktop startup failed", message);
    cleanup();
    app.quit();
  }
});
