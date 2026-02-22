const { app, BrowserWindow, Menu, Tray, dialog, ipcMain, screen, powerMonitor } = require("electron");
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

const isDev = process.env.MERCURYDESK_DESKTOP_DEV === "1" || !app.isPackaged;
const backendPort = Number(process.env.MERCURYDESK_BACKEND_PORT || (isDev ? 8000 : 18080));
const frontendPort = Number(process.env.MERCURYDESK_DESKTOP_PORT || (isDev ? 5173 : 1420));
const desktopZoom = Number(process.env.MERCURYDESK_DESKTOP_ZOOM || "1.0");
const PET_WINDOW_SIZE = 108;
const MAIN_ZOOM_MIN = 0.5;
const MAIN_ZOOM_MAX = 2.0;
const MAIN_ZOOM_STEP = 0.1;
const APP_USER_MODEL_ID = "com.ttawdtt.aelin";

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
let petStateLastKey = "";
let petLastState = "active";
let petCpuSnapshot = null;
let petPowerEventsBound = false;
let mainWindowPinned = false;

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
    active: pickGifByHints(files, ["active", "normal", "default", "action_02"], 0),
    idle: pickGifByHints(files, ["idle", "rest", "wait", "action_03"], 1),
    busy: pickGifByHints(files, ["busy", "alert", "hot", "action_04"], 2),
    sleep: pickGifByHints(files, ["sleep", "night", "zzz", "action_05"], 3),
    focus: pickGifByHints(files, ["focus", "monitor", "action_06"], 4),
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
  let state = "active";
  if (idleState === "locked" || idleSec >= 300) {
    state = "sleep";
  } else if (idleState === "idle" || idleSec >= 90) {
    state = "idle";
  } else if (route.startsWith("/processes")) {
    state = "focus";
  } else if (cpuUsage >= 0.78) {
    state = "busy";
  }
  petLastState = state;
  return {
    state,
    idleSec,
    idleState,
    cpuUsage: Number(cpuUsage.toFixed(3)),
    route,
    ts: Date.now(),
  };
}

function pushPetState(force = false) {
  if (!petWindow || petWindow.isDestroyed()) return;
  const payload = computePetRuntimeState();
  const key = `${payload.state}|${payload.idleState}|${Math.round(payload.cpuUsage * 100)}|${payload.route}`;
  if (!force && key === petStateLastKey) return;
  petStateLastKey = key;
  petWindow.webContents.send("pet:state", payload);
}

function stopPetStateTicker() {
  if (petStateTimer) {
    clearInterval(petStateTimer);
    petStateTimer = null;
  }
}

function startPetStateTicker() {
  stopPetStateTicker();
  petCpuSnapshot = null;
  sampleSystemCpuUsage();
  petStateTimer = setInterval(() => {
    pushPetState(false);
  }, 8000);
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
  };

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
    console.log(`[backend] Python runner selected: ${candidate.label}`);
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
  petPointerActive = next;
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

function ensurePetWindowCompactBounds() {
  if (!petWindow || petWindow.isDestroyed()) return null;
  let bounds = petWindow.getBounds();
  const target = PET_WINDOW_SIZE;
  const invalidSize = Math.abs(Number(bounds.width || 0) - target) > 2
    || Math.abs(Number(bounds.height || 0) - target) > 2;
  if (!invalidSize) return bounds;
  const before = {
    x: Number(bounds.x || 0),
    y: Number(bounds.y || 0),
    width: Number(bounds.width || 0),
    height: Number(bounds.height || 0),
  };
  try {
    if (typeof petWindow.isMaximized === "function" && petWindow.isMaximized()) {
      petWindow.unmaximize();
    }
  } catch {
    // ignore unmaximize failures
  }
  try {
    if (typeof petWindow.isFullScreen === "function" && petWindow.isFullScreen()) {
      petWindow.setFullScreen(false);
    }
  } catch {
    // ignore fullscreen reset failures
  }
  try {
    petWindow.restore();
  } catch {
    // ignore restore failures
  }
  try {
    petWindow.setResizable(true);
    petWindow.setMinimumSize(target, target);
    petWindow.setMaximumSize(target, target);
    petWindow.setBounds({
      x: Number(bounds.x || 0),
      y: Number(bounds.y || 0),
      width: target,
      height: target,
    }, false);
    petWindow.setResizable(false);
  } catch {
    // ignore set bounds failures
  }
  bounds = petWindow.getBounds();
  if (Math.abs(Number(bounds.width || 0) - target) > 2 || Math.abs(Number(bounds.height || 0) - target) > 2) {
    const cursor = getCursorDipPoint();
    const fallbackX = Math.round(Number(cursor.x || 0) - target / 2);
    const fallbackY = Math.round(Number(cursor.y || 0) - target / 2);
    try {
      petWindow.setBounds({
        x: fallbackX,
        y: fallbackY,
        width: target,
        height: target,
      }, false);
    } catch {
      // ignore fallback set bounds failures
    }
    bounds = petWindow.getBounds();
  }
  return bounds;
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
  const width = Number(bounds.width || PET_WINDOW_SIZE);
  const height = Number(bounds.height || PET_WINDOW_SIZE);
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
  const maxX = minX + Number(area.width || 0) - Number(bounds.width || PET_WINDOW_SIZE);
  const maxY = minY + Number(area.height || 0) - Number(bounds.height || PET_WINDOW_SIZE);
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
    const bounds = ensurePetWindowCompactBounds() || petWindow.getBounds();
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

  ipcMain.handle("pet:get-config", (event) => {
    if (!fromPet(event)) return {};
    return buildPetConfigPayload();
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
  const petSize = PET_WINDOW_SIZE;
  const display = screen.getPrimaryDisplay();
  const area = display?.workArea || { x: 0, y: 0, width: 1280, height: 720 };
  const x = area.x + area.width - petSize - 18;
  const y = area.y + area.height - petSize - 28;

  petWindow = new BrowserWindow({
    width: petSize,
    height: petSize,
    minWidth: petSize,
    minHeight: petSize,
    maxWidth: petSize,
    maxHeight: petSize,
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
  applyPetMouseMode();

  petWindow.loadFile(path.join(__dirname, "pet.html"), {
    query: {
      icon: `http://127.0.0.1:${frontendPort}/aelin-icon.ico`,
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
