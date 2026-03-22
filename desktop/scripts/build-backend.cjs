const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const backendDir = path.join(root, "backend");
const entryFile = path.join(backendDir, "scripts", "desktop_entry.py");
const requirementsFile = path.join(backendDir, "requirements.txt");
const distDir = path.join(backendDir, "dist");
const buildDir = path.join(backendDir, "build", "pyinstaller");
const runtimeDir = path.join(distDir, "aelin-backend");
const runtimeExe = path.join(runtimeDir, process.platform === "win32" ? "aelin-backend.exe" : "aelin-backend");
const venvDir = path.join(backendDir, ".desktop-build-venv");
const venvPython = path.join(venvDir, process.platform === "win32" ? "Scripts\\python.exe" : "bin/python");

function run(command, args, cwd = root) {
  const ret = spawnSync(command, args, {
    cwd,
    stdio: "inherit",
    shell: false,
    env: process.env,
  });
  if (ret.error) return false;
  return Number(ret.status) === 0;
}

function resolvePythonLaunchers() {
  const fromEnv = String(process.env.AELIN_PYTHON || "").trim();
  const launchers = [];
  if (fromEnv) launchers.push({ cmd: fromEnv, args: [] });
  launchers.push({ cmd: "python", args: [] });
  if (process.platform === "win32") launchers.push({ cmd: "py", args: ["-3"] });
  return launchers;
}

function pickPythonLauncher() {
  for (const launcher of resolvePythonLaunchers()) {
    if (run(launcher.cmd, [...launcher.args, "--version"], backendDir)) {
      return launcher;
    }
  }
  return null;
}

function ensureBuildVenv(launcher) {
  if (!fs.existsSync(venvPython)) {
    console.log(`[build-backend] Creating isolated build venv: ${venvDir}`);
    if (!run(launcher.cmd, [...launcher.args, "-m", "venv", venvDir], backendDir)) {
      console.error("[build-backend] Failed to create backend build venv.");
      process.exit(1);
    }
  }

  const refreshDeps = String(process.env.AELIN_REFRESH_BACKEND_VENV || "").trim() === "1";
  const pyInstallerReady = run(venvPython, ["-m", "PyInstaller", "--version"], backendDir);
  if (!pyInstallerReady || refreshDeps) {
    console.log("[build-backend] Installing backend build dependencies...");
    if (!run(venvPython, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], backendDir)) {
      console.error("[build-backend] Failed to upgrade pip toolchain in venv.");
      process.exit(1);
    }
    if (!run(venvPython, ["-m", "pip", "install", "-r", requirementsFile, "pyinstaller"], backendDir)) {
      console.error("[build-backend] Failed to install backend requirements or pyinstaller.");
      process.exit(1);
    }
  }

  if (!run(venvPython, ["-m", "PyInstaller", "--version"], backendDir)) {
    console.error("[build-backend] PyInstaller is unavailable in backend build venv.");
    process.exit(1);
  }
}

function main() {
  if (!fs.existsSync(entryFile)) {
    console.error(`[build-backend] backend entry not found: ${entryFile}`);
    process.exit(1);
  }

  const launcher = pickPythonLauncher();
  if (!launcher) {
    console.error("[build-backend] No usable Python launcher found. Set AELIN_PYTHON or install Python 3.");
    process.exit(1);
  }
  ensureBuildVenv(launcher);

  const args = [
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name",
    "aelin-backend",
    "--distpath",
    distDir,
    "--workpath",
    buildDir,
    "--specpath",
    buildDir,
    "--exclude-module",
    "pytest",
    "--exclude-module",
    "IPython",
    "--exclude-module",
    "matplotlib",
    "--exclude-module",
    "numpy",
    entryFile,
  ];

  console.log("[build-backend] Building backend runtime...");
  if (!run(venvPython, args, backendDir)) {
    process.exit(1);
  }

  if (!fs.existsSync(runtimeExe)) {
    console.error(`[build-backend] Built runtime missing executable: ${runtimeExe}`);
    process.exit(1);
  }

  console.log(`[build-backend] Runtime ready: ${runtimeExe}`);
}

main();
