const { app, BrowserWindow, dialog } = require("electron");
const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { spawn, spawnSync } = require("child_process");
const { StringDecoder } = require("string_decoder");

const isDev = process.env.MERCURYDESK_DESKTOP_DEV === "1" || !app.isPackaged;
const backendPort = Number(process.env.MERCURYDESK_BACKEND_PORT || (isDev ? 8000 : 18080));
const frontendPort = Number(process.env.MERCURYDESK_DESKTOP_PORT || (isDev ? 5173 : 1420));
const desktopZoom = Number(process.env.MERCURYDESK_DESKTOP_ZOOM || "1.0");

let mainWindow = null;
let backendProc = null;
let frontendDevProc = null;
let frontendServer = null;
let closing = false;

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

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 430,
    height: 860,
    minWidth: 390,
    minHeight: 700,
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

  const url = `http://127.0.0.1:${frontendPort}/?desktop=1&compact=1`;
  mainWindow.loadURL(url);
  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
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
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  cleanup();
});

app.whenReady().then(async () => {
  try {
    await boot();
    createMainWindow();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    dialog.showErrorBox("Aelin Desktop 启动失败", message);
    cleanup();
    app.quit();
  }
});
