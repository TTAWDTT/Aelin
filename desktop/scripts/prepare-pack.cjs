const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const frontendIndex = path.join(root, "frontend", "dist", "index.html");
const backendExe = path.join(
  root,
  "backend",
  "dist",
  "aelin-backend",
  process.platform === "win32" ? "aelin-backend.exe" : "aelin-backend"
);

const missing = [];
if (!fs.existsSync(frontendIndex)) missing.push(`frontend dist missing: ${frontendIndex}`);
if (!fs.existsSync(backendExe)) missing.push(`backend runtime missing: ${backendExe}`);

if (missing.length) {
  console.error("[prepare-pack] Missing build artifacts:");
  for (const item of missing) console.error(`- ${item}`);
  console.error("[prepare-pack] Run full build once:");
  console.error("  npm --prefix desktop run build:backend");
  console.error("  npm --prefix desktop run build:frontend");
  process.exit(1);
}

console.log("[prepare-pack] OK: using existing frontend dist + backend runtime.");
