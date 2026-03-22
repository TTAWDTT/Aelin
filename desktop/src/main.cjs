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

require("./aelin_desktop_runtime.cjs");

