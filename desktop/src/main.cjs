// Thin Electron entrypoint for Aelin Desktop.
//
// Historically, this file contained the entire desktop runtime (backend
// bootstrap, pet window, device plugin API, tray/menu wiring, etc.) and
// grew beyond 3k lines. To keep the entrypoint maintainable, the full
// runtime now lives in `aelin_desktop_runtime.cjs` and this file simply
// loads it.
//
// The runtime module attaches all required `app.whenReady` handlers and
// window/tray setup on import, so requiring it here is enough to start the
// desktop shell.

const fs = require("fs");
const path = require("path");
const { app, dialog } = require("electron");

function appendBootstrapLog(line) {
  const message = String(line ?? "");
  const configuredUserData = String(process.env.AELIN_USER_DATA_DIR || "").trim();
  const userDataDir = configuredUserData || app.getPath("userData");
  if (!userDataDir) return;
  try {
    const logDir = path.join(userDataDir, "logs");
    fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(path.join(logDir, "desktop-bootstrap.log"), `${new Date().toISOString()} ${message}\n`, "utf8");
  } catch {
    // ignore bootstrap log failures
  }
}

try {
  require("./aelin_desktop_runtime.cjs");
} catch (error) {
  const detail = error instanceof Error ? error.stack || error.message : String(error);
  appendBootstrapLog(`[bootstrap-failed] ${detail}`);
  try {
    dialog.showErrorBox("Aelin Desktop bootstrap failed", detail);
  } catch {
    // ignore dialog failures
  }
  throw error;
}
