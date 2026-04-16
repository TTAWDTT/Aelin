const { spawnSync } = require("child_process");
const crypto = require("crypto");
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
const venvStateFile = path.join(venvDir, ".aelin-build-state.json");
const pyInstallerDataSeparator = process.platform === "win32" ? ";" : ":";

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

function runQuiet(command, args, cwd = root) {
  const ret = spawnSync(command, args, {
    cwd,
    stdio: "ignore",
    shell: false,
    env: process.env,
  });
  if (ret.error) return false;
  return Number(ret.status) === 0;
}

function runCapture(command, args, cwd = root) {
  const ret = spawnSync(command, args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
    env: process.env,
    encoding: "utf8",
  });
  if (ret.error || Number(ret.status) !== 0) {
    return {
      ok: false,
      stdout: String(ret.stdout || ""),
      stderr: String(ret.stderr || ""),
    };
  }
  return {
    ok: true,
    stdout: String(ret.stdout || ""),
    stderr: String(ret.stderr || ""),
  };
}

function resolvePythonLaunchers() {
  const fromEnv = String(process.env.AELIN_PYTHON || "").trim();
  const launchers = [];
  if (fromEnv) launchers.push({ cmd: fromEnv, args: [] });
  launchers.push({ cmd: "python", args: [] });
  if (process.platform === "win32") launchers.push({ cmd: "py", args: ["-3"] });
  return launchers;
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function readVenvState() {
  if (!fs.existsSync(venvStateFile)) return null;
  try {
    return JSON.parse(fs.readFileSync(venvStateFile, "utf8"));
  } catch {
    return null;
  }
}

function writeVenvState(state) {
  fs.writeFileSync(venvStateFile, `${JSON.stringify(state, null, 2)}\n`, "utf8");
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
  const existingVenvUsable = fs.existsSync(venvPython) && runQuiet(venvPython, ["--version"], backendDir);
  if (!existingVenvUsable && fs.existsSync(venvDir)) {
    console.log(`[build-backend] Recreating broken build venv: ${venvDir}`);
    fs.rmSync(venvDir, { recursive: true, force: true });
  }

  if (!fs.existsSync(venvPython)) {
    console.log(`[build-backend] Creating isolated build venv: ${venvDir}`);
    if (!run(launcher.cmd, [...launcher.args, "-m", "venv", venvDir], backendDir)) {
      console.error("[build-backend] Failed to create backend build venv.");
      process.exit(1);
    }
  }

  const refreshDeps = String(process.env.AELIN_REFRESH_BACKEND_VENV || "").trim() === "1";
  const pyInstallerReady = run(venvPython, ["-m", "PyInstaller", "--version"], backendDir);
  const expectedState = {
    requirementsSha256: sha256File(requirementsFile),
  };
  const currentState = readVenvState();
  const depsOutOfDate = !currentState || currentState.requirementsSha256 !== expectedState.requirementsSha256;
  if (!pyInstallerReady || refreshDeps || depsOutOfDate) {
    console.log("[build-backend] Installing backend build dependencies...");
    if (!run(venvPython, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], backendDir)) {
      console.error("[build-backend] Failed to upgrade pip toolchain in venv.");
      process.exit(1);
    }
    if (!run(venvPython, ["-m", "pip", "install", "-r", requirementsFile, "pyinstaller"], backendDir)) {
      console.error("[build-backend] Failed to install backend requirements or pyinstaller.");
      process.exit(1);
    }
    writeVenvState(expectedState);
  }

  if (!run(venvPython, ["-m", "PyInstaller", "--version"], backendDir)) {
    console.error("[build-backend] PyInstaller is unavailable in backend build venv.");
    process.exit(1);
  }
}

function resolveLangGraphApiOpenapi() {
  const probe = runCapture(
    venvPython,
    [
      "-c",
      [
        "import pathlib",
        "import langgraph_api",
        "target = pathlib.Path(langgraph_api.__file__).resolve().parent.parent / 'openapi.json'",
        "print(target)",
      ].join("; "),
    ],
    backendDir
  );
  if (!probe.ok) {
    console.error("[build-backend] Failed to locate langgraph_api openapi.json from build venv.");
    if (probe.stderr.trim()) console.error(probe.stderr.trim());
    process.exit(1);
  }
  const openapiPath = path.resolve(probe.stdout.trim());
  if (!openapiPath || !fs.existsSync(openapiPath)) {
    console.error(`[build-backend] Missing langgraph_api openapi.json: ${openapiPath}`);
    process.exit(1);
  }
  return openapiPath;
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
  const langGraphApiOpenapi = resolveLangGraphApiOpenapi();

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
    "--hidden-import",
    "agent_server.auth",
    "--hidden-import",
    "agent_server.graph",
    "--hidden-import",
    "app.main",
    "--copy-metadata",
    "deepagents",
    "--copy-metadata",
    "langgraph",
    "--copy-metadata",
    "langgraph-api",
    "--copy-metadata",
    "langgraph-runtime-inmem",
    "--copy-metadata",
    "langsmith",
    "--collect-data",
    "langgraph_api",
    "--collect-data",
    "langgraph_runtime_inmem",
    "--add-data",
    `${langGraphApiOpenapi}${pyInstallerDataSeparator}.`,
    "--add-data",
    `${path.join(backendDir, "deepagents_skills")}${pyInstallerDataSeparator}deepagents_skills`,
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
