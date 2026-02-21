const { app, BrowserWindow, Menu, Tray, dialog, ipcMain, screen } = require("electron");
const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const { StringDecoder } = require("string_decoder");
const { getWindowPreset } = require("./window-presets.cjs");

const isDev = process.env.MERCURYDESK_DESKTOP_DEV === "1" || !app.isPackaged;
const backendPort = Number(process.env.MERCURYDESK_BACKEND_PORT || (isDev ? 8000 : 18080));
const frontendPort = Number(process.env.MERCURYDESK_DESKTOP_PORT || (isDev ? 5173 : 1420));
const desktopZoom = Number(process.env.MERCURYDESK_DESKTOP_ZOOM || "1.0");

let mainWindow = null;
let petWindow = null;
let tray = null;
let backendProc = null;
let frontendDevProc = null;
let frontendServer = null;
let closing = false;
let petDragState = null;
let petIpcHandlersRegistered = false;
let petPointerActive = false;

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

function applyMainWindowPreset(route = "/") {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const preset = resolveWindowPreset(route);
  mainWindow.setMinimumSize(preset.minWidth, preset.minHeight);
  mainWindow.setMaximumSize(preset.maxWidth, preset.maxHeight);
  const [currentW, currentH] = mainWindow.getSize();
  if (currentW !== preset.width || currentH !== preset.height) {
    mainWindow.setSize(preset.width, preset.height);
  }
  mainWindow.setResizable(false);
  mainWindow.setMaximizable(false);
  mainWindow.setFullScreenable(false);
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
      throw new Error(`内置后端不可用: ${exePath}`);
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
      dialog.showErrorBox("后端启动失败", String(err?.message || err));
    });
    return;
  }

  const root = backendDir();
  if (!fs.existsSync(root)) {
    throw new Error(`backend 目录不存在: ${root}`);
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
    const details = failed.length ? `\n候选失败:\n- ${failed.join("\n- ")}` : "";
    throw new Error(`无法启动后端 Python 进程。${details}`);
  }

  pipeTaggedLog(backendProc, "backend");
  backendProc.on("error", (err) => {
    if (closing) return;
    dialog.showErrorBox("后端启动失败", String(err?.message || err));
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
    throw new Error(`frontend dist 不存在: ${dist}，请先执行桌面构建流程中的前端 build。`);
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
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#111111",
    title: "Aelin",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const zoom = Number.isFinite(desktopZoom)
    ? Math.max(0.72, Math.min(1.15, desktopZoom))
    : 1.0;
  mainWindow.webContents.setZoomFactor(zoom);

  mainWindow.loadURL(buildAppUrl(initialRoute));
  mainWindow.once("ready-to-show", () => {
    if (showWhenReady) {
      mainWindow.show();
    }
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
    mainWindow = null;
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
}

function createPetMenu() {
  return Menu.buildFromTemplate([
    { label: "Chat", click: () => openModule("/") },
    { label: "Settings", click: () => openModule("/settings") },
    { label: "进程管理（Mac 风格）", click: () => openModule("/processes") },
    { label: "追踪 Web / 帖子", click: () => openModule("/tracking") },
    { label: "Aelinの日记", click: () => openModule("/diary") },
    { type: "separator" },
    { label: "专注模式", click: () => openModule("/focus") },
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
      petWindow.setAlwaysOnTop(true, "screen-saver");
      petWindow.focus();
    },
  });
}

function popupPetMenuAtCursor() {
  popupPetMenu();
}

function ensurePetVisible() {
  if (!petWindow || petWindow.isDestroyed()) {
    createPetWindow();
    return;
  }
  if (petWindow.isMinimized()) {
    petWindow.restore();
  }
  if (!petWindow.isVisible()) {
    petWindow.showInactive();
  }
  petWindow.setAlwaysOnTop(true, "screen-saver");
}

function setPetPointerActive(active) {
  if (!petWindow || petWindow.isDestroyed()) return;
  const next = !!active;
  if (petPointerActive === next) return;
  petPointerActive = next;
  // Passive mode: click-through window while still forwarding mouse move for hit-testing.
  petWindow.setIgnoreMouseEvents(!next, { forward: !next });
  if (!next) {
    petDragState = null;
  }
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
    const x = Number(payload?.screenX);
    const y = Number(payload?.screenY);
    const bounds = petWindow.getBounds();
    petDragState = {
      pointerX: Number.isFinite(x) ? x : bounds.x,
      pointerY: Number.isFinite(y) ? y : bounds.y,
      windowX: bounds.x,
      windowY: bounds.y,
    };
  });

  ipcMain.on("pet:drag-move", (event, payload) => {
    if (!fromPet(event) || !petWindow || petWindow.isDestroyed() || !petDragState) return;
    const x = Number(payload?.screenX);
    const y = Number(payload?.screenY);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const dx = x - petDragState.pointerX;
    const dy = y - petDragState.pointerY;
    petWindow.setPosition(Math.round(petDragState.windowX + dx), Math.round(petDragState.windowY + dy));
  });

  ipcMain.on("pet:drag-end", (event) => {
    if (!fromPet(event)) return;
    petDragState = null;
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
  tray.setContextMenu(createPetMenu());
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
  const petSize = 94;
  const display = screen.getPrimaryDisplay();
  const area = display?.workArea || { x: 0, y: 0, width: 1280, height: 720 };
  const x = area.x + area.width - petSize - 18;
  const y = area.y + area.height - petSize - 28;

  petWindow = new BrowserWindow({
    width: petSize,
    height: petSize,
    x,
    y,
    frame: false,
    transparent: true,
    hasShadow: false,
    resizable: false,
    movable: true,
    focusable: true,
    minimizable: false,
    maximizable: false,
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

  petWindow.setAlwaysOnTop(true, "screen-saver");
  petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  petWindow.setSkipTaskbar(true);
  petWindow.setMenuBarVisibility(false);
  petPointerActive = false;
  petWindow.setIgnoreMouseEvents(true, { forward: true });

  petWindow.loadFile(path.join(__dirname, "pet.html"), {
    query: {
      icon: `http://127.0.0.1:${frontendPort}/aelin-icon.ico`,
    },
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
    ensurePetVisible();
  });

  petWindow.on("hide", () => {
    if (closing) return;
    setTimeout(() => ensurePetVisible(), 30);
  });

  petWindow.on("blur", () => {
    if (!petWindow || petWindow.isDestroyed()) return;
    petWindow.setAlwaysOnTop(true, "screen-saver");
  });

  petWindow.on("closed", () => {
    petWindow = null;
    petDragState = null;
  });
}

async function boot() {
  startBackend();
  const backendReady = await waitForUrl(`http://127.0.0.1:${backendPort}/healthz`, 60000);
  if (!backendReady) {
    throw new Error(app.isPackaged ? "内置后端服务启动超时，请重装或反馈日志。" : "后端服务启动超时，请检查 Python 环境与依赖。");
  }

  if (isDev) {
    startFrontendDev();
  } else {
    startFrontendServer();
  }

  const frontendReady = await waitForUrl(`http://127.0.0.1:${frontendPort}`, 60000);
  if (!frontendReady) {
    throw new Error("前端服务启动超时。");
  }
}

function cleanup() {
  closing = true;
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
    createMainWindow("/", false);
    createPetWindow();
    createTray();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    dialog.showErrorBox("Aelin Desktop 启动失败", message);
    cleanup();
    app.quit();
  }
});
