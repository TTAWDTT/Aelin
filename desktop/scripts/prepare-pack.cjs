const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const frontendIndex = path.join(root, "frontend", "dist", "index.html");
const frontendIconIco = path.join(root, "frontend", "dist", "aelin-icon.ico");
const frontendIconPng = path.join(root, "frontend", "dist", "aelin-icon.png");
const backendExe = path.join(
  root,
  "backend",
  "dist",
  "aelin-backend",
  process.platform === "win32" ? "aelin-backend.exe" : "aelin-backend"
);
const desktopIconIco = path.join(root, "desktop", "build", "icon.ico");
const desktopIconPng = path.join(root, "desktop", "build", "icon.png");
const skipFreshnessCheck = String(process.env.AELIN_SKIP_ARTIFACT_FRESHNESS_CHECK || "").trim() === "1";

function latestMtime(targetPath) {
  if (!fs.existsSync(targetPath)) {
    return { mtimeMs: 0, path: targetPath };
  }
  const stat = fs.statSync(targetPath);
  if (stat.isFile()) {
    return { mtimeMs: stat.mtimeMs, path: targetPath };
  }
  let latest = { mtimeMs: stat.mtimeMs, path: targetPath };
  for (const entry of fs.readdirSync(targetPath, { withFileTypes: true })) {
    if (entry.name === "__pycache__" || entry.name === ".pytest_cache" || entry.name === "node_modules") {
      continue;
    }
    const child = latestMtime(path.join(targetPath, entry.name));
    if (child.mtimeMs > latest.mtimeMs) {
      latest = child;
    }
  }
  return latest;
}

function latestMtimeAmong(paths) {
  let latest = { mtimeMs: 0, path: "" };
  for (const item of paths) {
    const current = latestMtime(item);
    if (current.mtimeMs > latest.mtimeMs) {
      latest = current;
    }
  }
  return latest;
}

const missing = [];
if (!fs.existsSync(frontendIndex)) missing.push(`frontend dist missing: ${frontendIndex}`);
if (!fs.existsSync(frontendIconIco)) missing.push(`frontend icon missing: ${frontendIconIco}`);
if (!fs.existsSync(frontendIconPng)) missing.push(`frontend icon missing: ${frontendIconPng}`);
if (!fs.existsSync(backendExe)) missing.push(`backend runtime missing: ${backendExe}`);
if (!fs.existsSync(desktopIconIco)) missing.push(`desktop build icon missing: ${desktopIconIco}`);
if (!fs.existsSync(desktopIconPng)) missing.push(`desktop build icon missing: ${desktopIconPng}`);

if (missing.length) {
  console.error("[prepare-pack] Missing build artifacts:");
  for (const item of missing) console.error(`- ${item}`);
  console.error("[prepare-pack] Run a full build:");
  console.error("  npm --prefix desktop run build:backend");
  console.error("  npm --prefix desktop run build:frontend");
  process.exit(1);
}

if (!skipFreshnessCheck) {
  const frontendArtifactMtime = fs.statSync(frontendIndex).mtimeMs;
  const backendArtifactMtime = fs.statSync(backendExe).mtimeMs;

  const frontendSources = latestMtimeAmong([
    path.join(root, "frontend", "src"),
    path.join(root, "frontend", "public"),
    path.join(root, "frontend", "index.html"),
    path.join(root, "frontend", "package.json"),
    path.join(root, "frontend", "vite.config.ts"),
  ]);
  const backendSources = latestMtimeAmong([
    path.join(root, "backend", "app"),
    path.join(root, "backend", "agent_server"),
    path.join(root, "backend", "deepagents_skills"),
    path.join(root, "backend", "scripts", "desktop_entry.py"),
    path.join(root, "backend", "requirements.txt"),
    path.join(root, "backend", "langgraph.json"),
  ]);

  const stale = [];
  if (frontendArtifactMtime < frontendSources.mtimeMs) {
    stale.push(`frontend dist is older than source: ${frontendSources.path}`);
  }
  if (backendArtifactMtime < backendSources.mtimeMs) {
    stale.push(`backend runtime is older than source: ${backendSources.path}`);
  }

  if (stale.length) {
    console.error("[prepare-pack] Build artifacts are stale:");
    for (const item of stale) console.error(`- ${item}`);
    console.error("[prepare-pack] Use a fresh packaging build:");
    console.error("  npm --prefix desktop run dist:full");
    console.error("[prepare-pack] Or set AELIN_SKIP_ARTIFACT_FRESHNESS_CHECK=1 if you intentionally want to bypass this guard.");
    process.exit(1);
  }
}

console.log("[prepare-pack] OK: frontend dist and backend runtime are present and fresh enough for packaging.");
