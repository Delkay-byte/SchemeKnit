const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getAppInfo: () => ipcRenderer.invoke('get-app-info'),
  getBackendStatus: () => ipcRenderer.invoke('get-backend-status'),
  restartBackend: () => ipcRenderer.invoke('restart-backend'),
  backupData: () => ipcRenderer.invoke('backup-data'),
  saveFile: (options) => ipcRenderer.invoke('save-file', options),
  openFolder: (folderPath) => ipcRenderer.invoke('open-folder', folderPath),
  onBackendReady: (callback) => ipcRenderer.on('backend-ready', callback),
  onBackendStopped: (callback) => ipcRenderer.on('backend-stopped', callback),
  // Native menu actions from main process
  onMenuAction: (channel, callback) => {
    ipcRenderer.on(channel, (_event, ...args) => callback(...args));
  },
});
