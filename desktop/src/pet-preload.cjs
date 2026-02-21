const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("petBridge", {
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
});
