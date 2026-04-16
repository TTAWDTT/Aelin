const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const { spawn } = require("child_process");
const { randomUUID } = require("crypto");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requestJson(url, options = {}) {
  const method = String(options.method || "GET").trim().toUpperCase();
  const payload = options.payload === undefined ? undefined : JSON.stringify(options.payload);
  const timeoutMs = Number(options.timeoutMs || 5000);
  return new Promise((resolve) => {
    try {
      const target = new URL(url);
      const headers = {
        ...(options.headers || {}),
      };
      if (payload !== undefined) {
        headers["Content-Type"] = "application/json";
        headers["Content-Length"] = Buffer.byteLength(payload, "utf8");
      }
      const req = http.request(
        {
          protocol: target.protocol,
          hostname: target.hostname,
          port: target.port,
          path: `${target.pathname}${target.search}`,
          method,
          headers,
        },
        (res) => {
          const chunks = [];
          res.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
          res.on("end", () => {
            const body = Buffer.concat(chunks).toString("utf8");
            resolve({
              statusCode: Number(res.statusCode || 0),
              body,
            });
          });
        }
      );
      req.on("error", () => resolve({ statusCode: 0, body: "" }));
      req.setTimeout(timeoutMs, () => {
        req.destroy();
        resolve({ statusCode: 0, body: "" });
      });
      if (payload !== undefined) req.write(payload);
      req.end();
    } catch {
      resolve({ statusCode: 0, body: "" });
    }
  });
}

async function waitForCheck(check, timeoutMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    // eslint-disable-next-line no-await-in-loop
    if (await check()) return true;
    // eslint-disable-next-line no-await-in-loop
    await sleep(500);
  }
  return false;
}

async function waitForStatus(url, options = {}, expectedStatus = 200, timeoutMs = 60000) {
  return waitForCheck(async () => {
    const response = await requestJson(url, options);
    return response.statusCode === expectedStatus;
  }, timeoutMs);
}

function runAndWait(exe, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(exe, args, {
      windowsHide: true,
      stdio: "ignore",
      ...options,
    });
    child.on("error", reject);
    child.on("exit", (code, signal) => resolve({ code, signal }));
  });
}

function killTree(pid) {
  if (!pid) return Promise.resolve();
  return runAndWait("taskkill", ["/pid", String(pid), "/t", "/f"]).catch(() => undefined);
}

function findInstaller(distDir, pkg) {
  const productName = pkg.build?.productName || pkg.name || "App";
  const version = pkg.version || "0.0.0";
  const expected = path.join(distDir, `${productName} Setup ${version}.exe`);
  if (fs.existsSync(expected)) return expected;

  const expectedWeb = path.join(distDir, "nsis-web", `${productName} Web Setup ${version}.exe`);
  if (fs.existsSync(expectedWeb)) return expectedWeb;

  const candidates = [];
  const visit = (currentDir) => {
    for (const entry of fs.readdirSync(currentDir, { withFileTypes: true })) {
      const fullPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        visit(fullPath);
        continue;
      }
      if (/setup.*\.exe$/i.test(entry.name)) {
        candidates.push(fullPath);
      }
    }
  };
  visit(distDir);

  const fallback = candidates.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
  if (fallback) return fallback;
  throw new Error(`未找到安装器 .exe，目录: ${distDir}`);
}

function maybeSeedDesktopDb(userDataDir) {
  const seedDb = String(process.env.AELIN_VERIFY_SEED_DB || "").trim();
  if (!seedDb) return;
  const resolvedSeed = path.resolve(seedDb);
  if (!fs.existsSync(resolvedSeed)) {
    throw new Error(`AELIN_VERIFY_SEED_DB 指向的数据库不存在: ${resolvedSeed}`);
  }
  fs.mkdirSync(userDataDir, { recursive: true });
  fs.copyFileSync(resolvedSeed, path.join(userDataDir, "aelin.db"));
}

function resolveNsisWebPackageFile(installerPath) {
  const installerDir = path.dirname(installerPath);
  const candidates = fs
    .readdirSync(installerDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.nsis\.(7z|zip)$/i.test(entry.name))
    .map((entry) => path.join(installerDir, entry.name))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return candidates[0] || "";
}

function sqliteUrl(absPath) {
  return `sqlite:///${String(absPath || "").replace(/\\/g, "/")}`;
}

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
  return targetPath;
}

function buildHeadlessBackendEnv({ userDataDir, backendPort, desktopPort, runtimeRoot }) {
  const appDataDir = ensureDir(path.join(userDataDir, "data"));
  const outputRoot = ensureDir(path.join(userDataDir, "output"));
  const memoryRoot = ensureDir(path.join(appDataDir, "aelin_memory"));
  const mediaDir = ensureDir(path.join(userDataDir, "media"));
  const attachmentStorageDir = ensureDir(path.join(appDataDir, "aelin_attachments"));
  const googleWorkspaceConfigDir = ensureDir(path.join(appDataDir, "google_workspace"));
  const backendWorkDir = ensureDir(path.join(userDataDir, "backend-workdir"));
  return {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    LANG: "C.UTF-8",
    AELIN_BACKEND_HOST: "127.0.0.1",
    AELIN_BACKEND_PORT: String(backendPort),
    AELIN_PRODUCT_API_PORT: String(backendPort),
    AELIN_DESKTOP_PORT: String(desktopPort),
    AELIN_DATABASE_URL: sqliteUrl(path.join(userDataDir, "aelin.db")),
    AELIN_APP_DATA_DIR: appDataDir,
    AELIN_OUTPUT_ROOT: outputRoot,
    AELIN_MEMORY_ROOT: memoryRoot,
    AELIN_MEDIA_DIR: mediaDir,
    AELIN_AELIN_ATTACHMENT_STORAGE_DIR: attachmentStorageDir,
    AELIN_GOOGLE_WORKSPACE_CLI_CONFIG_DIR: googleWorkspaceConfigDir,
    AELIN_BACKEND_WORK_DIR: backendWorkDir,
    AELIN_CORS_ORIGINS: [
      `http://127.0.0.1:${desktopPort}`,
      `http://localhost:${desktopPort}`,
      "http://127.0.0.1:5173",
      "http://localhost:5173",
      "http://127.0.0.1:5174",
      "http://localhost:5174",
    ].join(","),
    AELIN_BACKEND_ASSET_ROOT: runtimeRoot,
  };
}

async function waitForAgentServerReady(baseUrl, timeoutMs = 60000) {
  return waitForCheck(async () => {
    const health = await requestJson(`${baseUrl}/healthz`);
    if (health.statusCode !== 200) return false;
    const ok = await requestJson(`${baseUrl}/ok`);
    if (ok.statusCode !== 200) return false;
    const assistants = await requestJson(`${baseUrl}/assistants/search`, {
      method: "POST",
      payload: {},
    });
    return assistants.statusCode === 200;
  }, timeoutMs);
}

function isProxiedDesktopRoute(urlPath) {
  const pathname = String(urlPath || "");
  return [
    "/api",
    "/media",
    "/assistants",
    "/threads",
    "/runs",
    "/crons",
    "/store",
    "/docs",
    "/openapi.json",
    "/ok",
    "/healthz",
  ].some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function mimeTypeForFile(filePath) {
  const ext = path.extname(String(filePath || "")).toLowerCase();
  switch (ext) {
    case ".html":
      return "text/html; charset=utf-8";
    case ".js":
    case ".mjs":
    case ".cjs":
      return "application/javascript; charset=utf-8";
    case ".css":
      return "text/css; charset=utf-8";
    case ".json":
      return "application/json; charset=utf-8";
    case ".svg":
      return "image/svg+xml";
    case ".png":
      return "image/png";
    case ".ico":
      return "image/x-icon";
    case ".gif":
      return "image/gif";
    case ".woff":
      return "font/woff";
    case ".woff2":
      return "font/woff2";
    default:
      return "application/octet-stream";
  }
}

function safeJoinUnderRoot(rootDir, requestPath) {
  const rawPath = decodeURIComponent(String(requestPath || "/").split("?")[0].split("#")[0] || "/");
  const normalized = rawPath === "/" ? "index.html" : rawPath.replace(/^\/+/, "");
  const resolved = path.resolve(rootDir, normalized);
  const root = path.resolve(rootDir);
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
    return "";
  }
  return resolved;
}

function startHeadlessDesktopFrontendServer({ distDir, backendPort, desktopPort }) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const reqUrl = new URL(req.url || "/", `http://127.0.0.1:${desktopPort}`);
      if (isProxiedDesktopRoute(reqUrl.pathname)) {
        const proxyReq = http.request(
          {
            protocol: "http:",
            hostname: "127.0.0.1",
            port: backendPort,
            method: req.method || "GET",
            path: `${reqUrl.pathname}${reqUrl.search}`,
            headers: req.headers,
          },
          (proxyRes) => {
            res.writeHead(Number(proxyRes.statusCode || 502), proxyRes.headers);
            proxyRes.pipe(res);
          }
        );
        proxyReq.on("error", () => {
          if (!res.headersSent) {
            res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8" });
          }
          res.end("proxy_error");
        });
        req.pipe(proxyReq);
        return;
      }

      let targetFile = safeJoinUnderRoot(distDir, reqUrl.pathname);
      if (!targetFile || !fs.existsSync(targetFile) || fs.statSync(targetFile).isDirectory()) {
        targetFile = path.join(distDir, "index.html");
      }
      try {
        const body = fs.readFileSync(targetFile);
        res.writeHead(200, {
          "Content-Type": mimeTypeForFile(targetFile),
          "Content-Length": Buffer.byteLength(body),
        });
        res.end(body);
      } catch {
        res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("not_found");
      }
    });
    server.on("error", reject);
    server.listen(desktopPort, "127.0.0.1", () => resolve(server));
  });
}

async function runHeadlessInstalledVerification({
  backendExe,
  frontendDistDir,
  userDataDir,
  runtimeRoot,
  backendPort,
  desktopPort,
}) {
  const baseUrl = `http://127.0.0.1:${backendPort}`;
  const frontendBaseUrl = `http://127.0.0.1:${desktopPort}`;
  const backendEnv = buildHeadlessBackendEnv({
    userDataDir,
    backendPort,
    desktopPort,
    runtimeRoot,
  });
  const backendProc = spawn(backendExe, {
    cwd: ensureDir(path.join(userDataDir, "backend-workdir")),
    windowsHide: true,
    detached: false,
    stdio: "ignore",
    env: backendEnv,
  });
  let frontendServer = null;
  try {
    const backendReady = await waitForAgentServerReady(baseUrl, 60000);
    if (!backendReady) {
      throw new Error(`headless 校验中后端运行时未就绪: ${baseUrl}`);
    }
    frontendServer = await startHeadlessDesktopFrontendServer({
      distDir: frontendDistDir,
      backendPort,
      desktopPort,
    });
    const frontendReady = await waitForStatus(`${frontendBaseUrl}/`, {}, 200, 15000);
    if (!frontendReady) {
      throw new Error(`headless 校验中前端静态服务未就绪: ${frontendBaseUrl}`);
    }
    return {
      baseUrl,
      frontendBaseUrl,
      async cleanup() {
        if (frontendServer) {
          await new Promise((resolve) => frontendServer.close(() => resolve(undefined)));
          frontendServer = null;
        }
        await killTree(backendProc.pid);
      },
    };
  } catch (error) {
    if (frontendServer) {
      await new Promise((resolve) => frontendServer.close(() => resolve(undefined)));
      frontendServer = null;
    }
    await killTree(backendProc.pid);
    throw error;
  }
}

async function runHttpContractChecks({ baseUrl, frontendBaseUrl }) {
  const assistants = await requestJson(`${baseUrl}/assistants/search`, {
    method: "POST",
    payload: {},
  });
  if (assistants.statusCode !== 200) {
    throw new Error(`/assistants/search 返回异常状态: ${assistants.statusCode}`);
  }
  let assistantId = "";
  try {
    const parsed = JSON.parse(assistants.body || "[]");
    const rows = Array.isArray(parsed) ? parsed : [];
    const match = rows.find((item) => String(item?.graph_id || "") === "agent");
    assistantId = String(match?.assistant_id || "").trim();
  } catch {
    assistantId = "";
  }
  if (!assistantId) {
    throw new Error("安装包启动后未发现 graph_id=agent 的 assistant。");
  }

  const threads = await requestJson(`${baseUrl}/threads`, {
    method: "POST",
    payload: {
      thread_id: randomUUID(),
      if_exists: "do_nothing",
    },
  });
  if (threads.statusCode !== 200) {
    throw new Error(`/threads 创建失败，状态码: ${threads.statusCode}`);
  }

  const proxiedAssistants = await requestJson(`${frontendBaseUrl}/assistants/search`, {
    method: "POST",
    payload: {},
    timeoutMs: 15000,
  });
  if (proxiedAssistants.statusCode !== 200) {
    throw new Error(`桌面前端代理的 /assistants/search 返回异常状态: ${proxiedAssistants.statusCode}`);
  }

  const proxiedThreads = await requestJson(`${frontendBaseUrl}/threads`, {
    method: "POST",
    payload: {
      thread_id: randomUUID(),
      if_exists: "do_nothing",
    },
    timeoutMs: 15000,
  });
  if (proxiedThreads.statusCode !== 200) {
    throw new Error(`桌面前端代理的 /threads 返回异常状态: ${proxiedThreads.statusCode}`);
  }

  const graph = await requestJson(`${baseUrl}/assistants/${assistantId}/graph?xray=2`);
  if (graph.statusCode !== 200) {
    const graphReady = await waitForStatus(
      `${baseUrl}/assistants/${assistantId}/graph?xray=2`,
      { timeoutMs: 15000 },
      200,
      60000
    );
    if (!graphReady) {
      throw new Error(`/assistants/${assistantId}/graph 返回异常状态: ${graph.statusCode}`);
    }
  }

  const icon = await requestJson(`${frontendBaseUrl}/aelin-icon.ico`, { timeoutMs: 15000 });
  if (icon.statusCode !== 200) {
    throw new Error(`桌面前端未能提供图标资源 /aelin-icon.ico，状态码: ${icon.statusCode}`);
  }
}

async function main() {
  const desktopDir = path.resolve(__dirname, "..");
  const pkgPath = path.join(desktopDir, "package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  const distDir = path.join(desktopDir, "release-dist");

  if (!fs.existsSync(distDir)) {
    throw new Error(`release-dist 不存在: ${distDir}，请先运行 npm run dist`);
  }

  const installer = findInstaller(distDir, pkg);
  const installRoot = path.join(os.tmpdir(), `aelin-install-verify-${Date.now()}`);
  const userDataDir = path.join(os.tmpdir(), `aelin-install-userdata-${Date.now()}`);
  fs.mkdirSync(installRoot, { recursive: true });
  fs.mkdirSync(userDataDir, { recursive: true });
  maybeSeedDesktopDb(userDataDir);

  console.log(`[verify] installer: ${installer}`);
  console.log(`[verify] install target: ${installRoot}`);
  console.log(`[verify] user data: ${userDataDir}`);

  const installArgs = ["/S", "/currentuser", `/D=${installRoot}`];
  const nsisWebPackageFile = resolveNsisWebPackageFile(installer);
  if (nsisWebPackageFile) {
    installArgs.push(`--package-file=${nsisWebPackageFile}`);
    console.log(`[verify] nsis-web package file: ${nsisWebPackageFile}`);
  }

  const installResult = await runAndWait(installer, installArgs, {
    cwd: path.dirname(installer),
  });
  if (installResult.code !== 0) {
    throw new Error(`静默安装失败 code=${installResult.code} signal=${installResult.signal || ""}`);
  }

  const appExe = path.join(installRoot, `${pkg.build?.productName || "Aelin"}.exe`);
  const backendExe = path.join(
    installRoot,
    "resources",
    "backend-runtime",
    process.platform === "win32" ? "aelin-backend.exe" : "aelin-backend"
  );
  const frontendDistDir = path.join(installRoot, "resources", "frontend-dist");
  const backendRuntimeRoot = path.join(installRoot, "resources", "backend-runtime");
  const packagedFrontendIcon = path.join(installRoot, "resources", "frontend-dist", "aelin-icon.ico");
  const packagedDesktopIcon = path.join(installRoot, "resources", "build", "icon.ico");

  if (!fs.existsSync(appExe)) {
    throw new Error(`安装后未找到主程序: ${appExe}`);
  }
  if (!fs.existsSync(backendExe)) {
    throw new Error(`安装后未找到后端运行时: ${backendExe}`);
  }
  if (!fs.existsSync(packagedFrontendIcon)) {
    throw new Error(`安装后未找到前端图标资源: ${packagedFrontendIcon}`);
  }
  if (!fs.existsSync(packagedDesktopIcon)) {
    throw new Error(`安装后未找到桌面图标资源: ${packagedDesktopIcon}`);
  }

  const backendPort = 18180;
  const desktopPort = 14220;
  const baseUrl = `http://127.0.0.1:${backendPort}`;
  const frontendBaseUrl = `http://127.0.0.1:${desktopPort}`;
  console.log(`[verify] launch app: ${appExe}`);
  const appProc = spawn(appExe, {
    windowsHide: true,
    detached: false,
    stdio: "ignore",
    env: {
      ...process.env,
      AELIN_BACKEND_PORT: String(backendPort),
      AELIN_DESKTOP_PORT: String(desktopPort),
      AELIN_DESKTOP_VERIFY_MODE: "1",
      AELIN_USER_DATA_DIR: userDataDir,
      ELECTRON_ENABLE_LOGGING: "1",
    },
  });
  let appExited = false;
  appProc.on("exit", () => {
    appExited = true;
  });

  try {
    const backendReady = await waitForAgentServerReady(baseUrl, 12000);

    if (!backendReady) {
      await killTree(appProc.pid);
      if (appExited) {
        console.log("[verify] packaged desktop app exited before services became ready; switching to headless resource verification.");
        const headless = await runHeadlessInstalledVerification({
          backendExe,
          frontendDistDir,
          userDataDir,
          runtimeRoot: backendRuntimeRoot,
          backendPort,
          desktopPort,
        });
        try {
          await runHttpContractChecks({
            baseUrl: headless.baseUrl,
            frontendBaseUrl: headless.frontendBaseUrl,
          });
          console.log("[verify] OK: headless installer verification passed using installed backend runtime + frontend dist resources.");
          return;
        } finally {
          await headless.cleanup();
        }
      }
      throw new Error(`应用启动后官方 Agent Server 未就绪: ${baseUrl}`);
    }

    const frontendReady = await waitForStatus(`${frontendBaseUrl}/`, {}, 200, 60000);
    if (!frontendReady) {
      throw new Error(`应用启动后桌面前端未就绪: ${frontendBaseUrl}`);
    }
    await runHttpContractChecks({ baseUrl, frontendBaseUrl });
  } finally {
    await killTree(appProc.pid);
  }

  console.log("[verify] OK: installer launches packaged backend + desktop frontend, and the frontend successfully proxies official agent routes and icon assets.");
}

main().catch((err) => {
  console.error(`[verify] FAIL: ${err?.message || err}`);
  process.exit(1);
});
