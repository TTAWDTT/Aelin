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

  const fallback = fs
    .readdirSync(distDir)
    .filter((f) => /setup.*\.exe$/i.test(f))
    .map((f) => path.join(distDir, f))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];

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

  const installResult = await runAndWait(installer, ["/S", "/currentuser", `/D=${installRoot}`]);
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
      AELIN_USER_DATA_DIR: userDataDir,
      ELECTRON_ENABLE_LOGGING: "1",
    },
  });

  try {
    const backendReady = await waitForCheck(async () => {
      const health = await requestJson(`${baseUrl}/healthz`);
      if (health.statusCode !== 200) return false;
      const ok = await requestJson(`${baseUrl}/ok`);
      if (ok.statusCode !== 200) return false;
      const assistants = await requestJson(`${baseUrl}/assistants/search`, {
        method: "POST",
        payload: {},
      });
      return assistants.statusCode === 200;
    }, 60000);

    if (!backendReady) {
      throw new Error(`应用启动后官方 Agent Server 未就绪: ${baseUrl}`);
    }

    const frontendReady = await waitForStatus(`${frontendBaseUrl}/`, {}, 200, 60000);
    if (!frontendReady) {
      throw new Error(`应用启动后桌面前端未就绪: ${frontendBaseUrl}`);
    }

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
  } finally {
    await killTree(appProc.pid);
  }

  console.log("[verify] OK: installer launches packaged backend + desktop frontend, and the frontend successfully proxies official agent routes and icon assets.");
}

main().catch((err) => {
  console.error(`[verify] FAIL: ${err?.message || err}`);
  process.exit(1);
});
