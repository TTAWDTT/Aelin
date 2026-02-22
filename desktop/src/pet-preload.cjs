const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("petBridge", {
  setPointerActive(active) {
    ipcRenderer.send("pet:set-pointer-active", { active: !!active });
  },
  openMenu(payload) {
    ipcRenderer.send("pet:open-menu", payload || {});
  },
  openChat() {
    ipcRenderer.send("pet:open-chat");
  },
  dragStart(payload) {
    ipcRenderer.send("pet:drag-start", payload || {});
  },
  dragMove(payload) {
    ipcRenderer.send("pet:drag-move", payload || {});
  },
  dragEnd() {
    ipcRenderer.send("pet:drag-end");
  },
  getConfig() {
    return ipcRenderer.invoke("pet:get-config");
  },
  onState(callback) {
    if (typeof callback !== "function") return () => {};
    const handler = (_event, payload) => callback(payload || {});
    ipcRenderer.on("pet:state", handler);
    return () => ipcRenderer.removeListener("pet:state", handler);
  },
  onConfig(callback) {
    if (typeof callback !== "function") return () => {};
    const handler = (_event, payload) => callback(payload || {});
    ipcRenderer.on("pet:config", handler);
    return () => ipcRenderer.removeListener("pet:config", handler);
  },
});
