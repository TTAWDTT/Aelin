const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const { spawn } = require("child_process");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requestOk(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      const code = Number(res.statusCode || 0);
      res.resume();
      resolve(code >= 200 && code < 300);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForUrl(url, timeoutMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    // eslint-disable-next-line no-await-in-loop
    if (await requestOk(url)) return true;
    // eslint-disable-next-line no-await-in-loop
    await sleep(500);
  }
  return false;
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

async function main() {
  const desktopDir = path.resolve(__dirname, "..");
  const pkgPath = path.join(desktopDir, "package.json");
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  const distDir = path.join(desktopDir, "release-dist");

  if (!fs.existsSync(distDir)) {
    throw new Error(`release-dist 不存在: ${distDir}，请先运行 npm run dist`);
  }

  const installer = findInstaller(distDir, pkg);
  const targetDir = path.join(os.tmpdir(), `aelin-install-verify-${Date.now()}`);
  fs.mkdirSync(targetDir, { recursive: true });

  console.log(`[verify] installer: ${installer}`);
  console.log(`[verify] install target: ${targetDir}`);

  // NSIS: /D must be the last argument and should be unquoted.
  // For assisted NSIS (oneClick=false), explicitly force current-user mode in silent install.
  const installResult = await runAndWait(installer, ["/S", "/currentuser", `/D=${targetDir}`]);
  if (installResult.code !== 0) {
    throw new Error(`静默安装失败 code=${installResult.code} signal=${installResult.signal || ""}`);
  }

  const appExe = path.join(targetDir, `${pkg.build?.productName || "Aelin"}.exe`);
  const backendExe = path.join(targetDir, "resources", "backend-runtime", process.platform === "win32" ? "aelin-backend.exe" : "aelin-backend");

  if (!fs.existsSync(appExe)) {
    throw new Error(`安装后未找到主程序: ${appExe}`);
  }
  if (!fs.existsSync(backendExe)) {
    throw new Error(`安装后未找到后端运行时: ${backendExe}`);
  }

  const backendPort = 18180;
  const desktopPort = 14220;
  console.log(`[verify] launch app: ${appExe}`);
  const appProc = spawn(appExe, {
    windowsHide: true,
    detached: false,
    stdio: "ignore",
    env: {
      ...process.env,
      MERCURYDESK_BACKEND_PORT: String(backendPort),
      MERCURYDESK_DESKTOP_PORT: String(desktopPort),
      ELECTRON_ENABLE_LOGGING: "1",
    },
  });

  const ok = await waitForUrl(`http://127.0.0.1:${backendPort}/healthz`, 60000);
  await killTree(appProc.pid);

  if (!ok) {
    throw new Error(`应用启动后后端健康检查失败: http://127.0.0.1:${backendPort}/healthz`);
  }

  console.log("[verify] OK: installer includes backend runtime and healthz is reachable.");
}

main().catch((err) => {
  console.error(`[verify] FAIL: ${err?.message || err}`);
  process.exit(1);
});
