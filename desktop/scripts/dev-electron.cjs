const { spawn } = require("child_process");
const path = require("path");

const electronPath = require("electron");
const cwd = path.resolve(__dirname, "..");
const env = {
  ...process.env,
  MERCURYDESK_DESKTOP_DEV: "1",
};

delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electronPath, ["."], {
  cwd,
  env,
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(Number.isInteger(code) ? code : 0);
});

