const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const desktopDir = path.resolve(__dirname, "..");
const distDir = path.join(desktopDir, "release-dist");
const pkg = JSON.parse(fs.readFileSync(path.join(desktopDir, "package.json"), "utf8"));
const electronBuilderBin = path.join(
  desktopDir,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "electron-builder.cmd" : "electron-builder"
);

function findExpectedInstaller() {
  const productName = pkg.build?.productName || pkg.name || "App";
  const version = pkg.version || "0.0.0";
  return path.join(distDir, `${productName} Setup ${version}.exe`);
}

function isRecoverableNsisMmapError(output) {
  return /Internal compiler error #12345: error creating mmap/i.test(String(output || ""));
}

function hasFreshInstallerArtifacts(startedAtMs) {
  const installerPath = findExpectedInstaller();
  const uninstallerPath = path.join(distDir, "__uninstaller-nsis-aelin-desktop.exe");
  const unpackedDir = path.join(distDir, "win-unpacked");
  if (!fs.existsSync(installerPath) || !fs.existsSync(uninstallerPath) || !fs.existsSync(unpackedDir)) {
    return false;
  }
  try {
    const installerStat = fs.statSync(installerPath);
    const uninstallerStat = fs.statSync(uninstallerPath);
    return installerStat.mtimeMs >= startedAtMs - 1000 && uninstallerStat.mtimeMs >= startedAtMs - 1000;
  } catch {
    return false;
  }
}

function main() {
  const startedAtMs = Date.now();
  const result = process.platform === "win32"
    ? spawnSync(
        electronBuilderBin,
        ["--config.directories.output=release-dist"],
        {
          shell: true,
          cwd: desktopDir,
          env: process.env,
          encoding: "utf8",
          stdio: ["inherit", "pipe", "pipe"],
        }
      )
    : spawnSync(
        electronBuilderBin,
        ["--config.directories.output=release-dist"],
        {
          cwd: desktopDir,
          env: process.env,
          encoding: "utf8",
          stdio: ["inherit", "pipe", "pipe"],
        }
      );

  const stdout = String(result.stdout || "");
  const stderr = String(result.stderr || "");
  if (stdout) process.stdout.write(stdout);
  if (stderr) process.stderr.write(stderr);

  if (result.error) {
    console.error(String(result.error?.message || result.error));
    process.exit(1);
    return;
  }

  if (Number(result.status ?? 1) === 0) {
    process.exit(0);
    return;
  }

  const combined = `${stdout}\n${stderr}`;
  if (isRecoverableNsisMmapError(combined) && hasFreshInstallerArtifacts(startedAtMs)) {
    const installerPath = findExpectedInstaller();
    console.warn(
      `[dist] NSIS reported a late mmap failure, but fresh installer artifacts already exist: ${installerPath}`
    );
    console.warn("[dist] Continuing so follow-up verification can validate the produced installer.");
    process.exit(0);
    return;
  }

  process.exit(Number(result.status ?? 1));
}

main();
