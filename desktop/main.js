const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const url = require('url');

let mainWindow = null;
let backendProcess = null;
let frontendServer = null;
let backendReady = false;
const BACKEND_PORT = 18234;
const FRONTEND_PORT = 18235;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/api/health`;
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`;

const isDev = !app.isPackaged;
const userDataPath = app.getPath('userData');
const appDataPath = path.join(userDataPath, 'data');
const uploadsPath = path.join(appDataPath, 'uploads');
const exportsPath = path.join(appDataPath, 'exports');
const tempPath = path.join(appDataPath, 'temp');
const dbPath = path.join(appDataPath, 'teachflow.db');

const logPath = path.join(appDataPath, 'diagnostics.log');
function diagLog(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  try {
    fs.appendFileSync(logPath, line);
  } catch (e) {
    // ignore
  }
  console.log(line.trim());
}

function ensureDirectories() {
  // Brand migration guard (TeachFlow -> SchemeKnit): userData resolves from
  // productName, so a renamed build would otherwise start on an empty profile
  // and orphan an existing desktop user's lessons. If the legacy data dir
  // exists and the current one does not, carry it across once, in place.
  try {
    const legacyDataPath = path.join(path.dirname(userDataPath), 'TeachFlow', 'data');
    if (fs.existsSync(legacyDataPath) && !fs.existsSync(appDataPath)) {
      fs.mkdirSync(path.dirname(appDataPath), { recursive: true });
      fs.renameSync(legacyDataPath, appDataPath);
      diagLog(`Migrated legacy data from ${legacyDataPath} to ${appDataPath}`);
    }
  } catch (e) {
    // Non-fatal: a failed migration must not block startup.
    diagLog(`Legacy data migration skipped: ${e.message}`);
  }
  [appDataPath, uploadsPath, exportsPath, tempPath].forEach(dir => {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  });
}

// Per-installation secrets for the local backend. The backend refuses to boot
// with default secrets (production fail-fast), so the desktop generates strong
// random values once, persists them in per-user app data, and reuses them
// across restarts (token continuity). Never shipped, never committed.
const crypto = require('crypto');

function getOrCreateSecrets() {
  const secretsPath = path.join(appDataPath, '.secrets.json');
  try {
    const parsed = JSON.parse(fs.readFileSync(secretsPath, 'utf8'));
    if (parsed && parsed.SECRET_KEY && parsed.JWT_SECRET_KEY) {
      return parsed;
    }
  } catch (e) {
    // missing or corrupt -> generate fresh below
  }
  const fresh = {
    SECRET_KEY: crypto.randomBytes(48).toString('base64'),
    JWT_SECRET_KEY: crypto.randomBytes(48).toString('base64'),
  };
  try {
    fs.writeFileSync(secretsPath, JSON.stringify(fresh), { mode: 0o600 });
  } catch (e) {
    diagLog('Could not persist secrets file: ' + e.message);
  }
  return fresh;
}

function getBackendDir() {
  if (isDev) {
    return path.join(__dirname, '..', 'backend');
  }
  return path.join(process.resourcesPath, 'backend');
}

function getBackendPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'backend', 'venv', 'Scripts', 'python.exe');
  }
  return path.join(process.resourcesPath, 'backend', 'schemeknit-backend.exe');
}

function getBackendArgs() {
  if (isDev) {
    return ['-m', 'uvicorn', 'src.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)];
  }
  return ['--host', '127.0.0.1', '--port', String(BACKEND_PORT)];
}

function getFrontendPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'frontend', 'out');
  }
  return path.join(process.resourcesPath, 'frontend');
}

// ============================================================
// FRONTEND STATIC FILE SERVER
// ============================================================

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml',
  '.map': 'application/json',
  '.webp': 'image/webp',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
};

function serveStaticFile(filePath, res) {
  try {
    const content = fs.readFileSync(filePath);
    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    res.writeHead(200, {
      'Content-Type': contentType,
      'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=31536000',
    });
    res.end(content);
    return true;
  } catch (e) {
    return false;
  }
}

function createFrontendServer() {
  const frontendPath = getFrontendPath();

  diagLog('Frontend server root: ' + frontendPath);
  diagLog('Frontend path exists: ' + fs.existsSync(frontendPath));

  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      try {
        const parsedUrl = new URL(req.url, `http://127.0.0.1:${FRONTEND_PORT}`);
        let pathname = decodeURIComponent(parsedUrl.pathname);

        // Security: prevent path traversal
        if (pathname.includes('..')) {
          res.writeHead(403);
          res.end('Forbidden');
          return;
        }

        // Strip leading slash for path joining
        const relativePath = pathname.startsWith('/') ? pathname.slice(1) : pathname;
        let filePath = path.join(frontendPath, relativePath);

        // Dynamic route fallback: /review/[id] -> /review/placeholder
        // Next.js static export only pre-renders placeholder params
        const dynamicMatch = relativePath.match(/^(review|generate|lessons)\/[^/]+\/?$/);
        if (dynamicMatch) {
          const dynamicBase = dynamicMatch[1];
          const placeholderPath = path.join(frontendPath, dynamicBase, 'placeholder', 'index.html');
          if (serveStaticFile(placeholderPath, res)) return;
        }

        // If path has no extension and doesn't end with /, check as directory first
        const ext = path.extname(pathname);

        // 1. Try serving as a file directly
        if (ext && serveStaticFile(filePath, res)) return;

        // 2. Try with .html extension (e.g., /dashboard -> dashboard.html)
        if (serveStaticFile(filePath + '.html', res)) return;

        // 3. Try as directory with index.html (e.g., /admin/ -> admin/index.html)
        if (serveStaticFile(path.join(filePath, 'index.html'), res)) return;

        // 4. Try as directory with trailing slash
        if (pathname.endsWith('/') && serveStaticFile(path.join(frontendPath, relativePath, 'index.html'), res)) return;

        // 5. SPA fallback: serve root index.html for client-side routing
        if (serveStaticFile(path.join(frontendPath, 'index.html'), res)) return;

        // 6. Final fallback: 404
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('Not Found');
      } catch (err) {
        diagLog('Frontend server error: ' + err.message);
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        res.end('Internal Server Error');
      }
    });

    server.on('error', (err) => {
      diagLog('Frontend server error: ' + err.message);
      reject(err);
    });

    server.listen(FRONTEND_PORT, '127.0.0.1', () => {
      diagLog('Frontend server listening on ' + FRONTEND_URL);
      resolve(server);
    });
  });
}

function stopFrontendServer() {
  if (frontendServer) {
    try {
      frontendServer.close();
    } catch (e) {
      diagLog('Error stopping frontend server: ' + e.message);
    }
    frontendServer = null;
  }
}

// ============================================================
// BACKEND MANAGEMENT
// ============================================================

function waitForBackend(timeout = 30000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      const req = http.get(HEALTH_URL, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const json = JSON.parse(data);
            if (json.status === 'healthy') {
              backendReady = true;
              diagLog('Backend health check OK');
              resolve(true);
            } else {
              retry();
            }
          } catch {
            retry();
          }
        });
      });
      req.on('error', retry);
      req.setTimeout(2000, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (Date.now() - start > timeout) {
        reject(new Error('Backend startup timeout after ' + (timeout/1000) + 's'));
      } else {
        setTimeout(check, 1000);
      }
    };
    check();
  });
}

function startBackend() {
  const backendPath = getBackendPath();
  const backendDir = getBackendDir();
  const args = getBackendArgs();

  diagLog('=== Backend Startup ===');
  diagLog('isDev: ' + isDev);
  diagLog('process.resourcesPath: ' + process.resourcesPath);
  diagLog('backendPath: ' + backendPath);
  diagLog('backendDir: ' + backendDir);
  diagLog('backend exists: ' + fs.existsSync(backendPath));
  diagLog('backendDir exists: ' + fs.existsSync(backendDir));

  if (!fs.existsSync(backendPath)) {
    diagLog('ERROR: Backend executable not found');
    showBackendError('Backend executable not found at: ' + backendPath);
    return;
  }

  const secrets = getOrCreateSecrets();
  const env = {
    ...process.env,
    DATABASE_URL: 'sqlite:///' + dbPath.replace(/\\/g, '/'),
    UPLOAD_DIR: uploadsPath,
    EXPORT_DIR: exportsPath,
    TEMP_DIR: tempPath,
    HOST: '127.0.0.1',
    PORT: String(BACKEND_PORT),
    SECRET_KEY: secrets.SECRET_KEY,
    JWT_SECRET_KEY: secrets.JWT_SECRET_KEY,
    CORS_ORIGINS: JSON.stringify([
      'http://localhost:3000',
      'http://127.0.0.1:3000',
      `http://127.0.0.1:${FRONTEND_PORT}`,
      `http://localhost:${FRONTEND_PORT}`,
      'http://127.0.0.1:18234',
      'file://',
    ]),
    AI_MODE: 'OFF',
    DEBUG: 'false',
    // Local evaluation profile: the backend enforces strong secrets but
    // allows the local architecture (SQLite + local storage + 127.0.0.1 CORS)
    // that this build is designed around. Public web deploys never set this.
    DESKTOP_MODE: '1',
  };

  // Point the backend at the bundled LibreOffice for offline PDF export.
  if (!isDev) {
    const loExe = path.join(process.resourcesPath, 'libreoffice', 'program', 'soffice.exe');
    if (fs.existsSync(loExe)) {
      env.LIBREOFFICE_PATH = loExe;
      diagLog('Bundled LibreOffice: ' + loExe);
    }
  } else {
    // In dev mode, try the system-installed LibreOffice
    const { execFileSync } = require('child_process');
    try {
      const loPath = execFileSync('where', ['soffice.exe'], { encoding: 'utf8', timeout: 3000 }).trim().split('\n')[0];
      if (loPath && fs.existsSync(loPath)) {
        env.LIBREOFFICE_PATH = loPath;
        diagLog('Dev LibreOffice: ' + loPath);
      }
    } catch (_) {
      diagLog('No system LibreOffice found for dev mode');
    }
  }

  if (!isDev) {
    const internalDir = path.join(backendDir, '_internal');
    env.PATH = backendDir + ';' + internalDir + ';' + (env.PATH || '');
  }

  diagLog('Backend env PATH: ' + (env.PATH || 'not set').substring(0, 200));

  try {
    backendProcess = spawn(backendPath, args, {
      env,
      cwd: backendDir,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });

    diagLog('Backend process spawned, PID: ' + backendProcess.pid);

    backendProcess.stdout.on('data', (data) => {
      const msg = data.toString().trim();
      diagLog('[STDOUT] ' + msg);
    });

    backendProcess.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      diagLog('[STDERR] ' + msg);
    });

    backendProcess.on('error', (err) => {
      diagLog('Backend spawn error: ' + err.message);
      showBackendError('Failed to start backend: ' + err.message);
    });

    backendProcess.on('exit', (code) => {
      diagLog('Backend exited with code: ' + code);
      backendReady = false;
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('backend-stopped', code);
      }
    });
  } catch (err) {
    diagLog('Failed to spawn backend: ' + err.message);
    showBackendError('Failed to spawn backend process: ' + err.message);
  }
}

function stopBackend() {
  if (backendProcess) {
    try {
      backendProcess.kill();
    } catch (e) {
      diagLog('Error killing backend: ' + e.message);
    }
    backendProcess = null;
    backendReady = false;
  }
}

function showBackendError(message) {
  diagLog('Showing backend error: ' + message);
  if (mainWindow && !mainWindow.isDestroyed()) {
    dialog.showMessageBox(mainWindow, {
      type: 'error',
      title: 'SchemeKnit - Backend Error',
      message: 'SchemeKnit could not start its local service.',
      detail: message,
      buttons: ['Retry', 'Close SchemeKnit'],
    }).then(({ response }) => {
      if (response === 0) {
        stopBackend();
        startBackend();
        waitForBackend().then(() => {
          notifyFrontendReady();
        }).catch(() => {
          showBackendError('Backend still failed to start.');
        });
      } else {
        app.quit();
      }
    });
  } else {
    dialog.showMessageBox({
      type: 'error',
      title: 'SchemeKnit - Backend Error',
      message: 'SchemeKnit could not start its local service.',
      detail: message,
      buttons: ['Close'],
    }).then(() => { app.quit(); });
  }
}

function notifyFrontendReady() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend-ready');
  }
}

function reloadFrontend() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(FRONTEND_URL);
  }
}

// ============================================================
// WINDOW CREATION
// ============================================================

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 768,
    title: 'SchemeKnit',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    show: false,
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
  } else {
    diagLog('Loading frontend URL: ' + FRONTEND_URL);
    mainWindow.loadURL(FRONTEND_URL);
  }

  // Log console messages for diagnostics in packaged builds
  if (!isDev) {
    mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
      const levels = ['verbose', 'info', 'warning', 'error'];
      const levelStr = levels[level] || 'unknown';
      diagLog(`[CONSOLE ${levelStr}] ${message} (${sourceId}:${line})`);
    });

    // Capture render process crashes
    mainWindow.webContents.on('render-process-gone', (event, details) => {
      diagLog('RENDER PROCESS GONE: ' + details.reason + ' - ' + (details.exitCode || ''));
    });
  }

  // Handle did-fail-load for diagnostics
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    diagLog('Frontend load failed: ' + errorCode + ' ' + errorDescription + ' URL: ' + validatedURL);
  });

  // Handle window close
  mainWindow.on('close', (e) => {
    if (backendProcess) {
      e.preventDefault();
      stopBackend();
      app.quit();
    }
  });
}

// ============================================================
// NATIVE APPLICATION MENU
// ============================================================

/**
 * Build the native application menu.
 *
 * File   - scheme/upload/save/print/sign-out/exit
 * Edit   - standard text editing (roles)
 * View   - reload/zoom/devtools/fullscreen (roles)
 * Help   - docs, shortcuts, report problem, about
 *
 * Navigation items send an IPC event to the renderer, which owns routing
 * (the frontend is a static export served over HTTP; the renderer can
 * push routes via its own router). The main process never touches URLs
 * of the SPA directly beyond loading the initial frontend root.
 */
function buildAppMenu() {
  const isMac = process.platform === 'darwin';

  const navigate = (path) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('menu:navigate', path);
    }
  };

  const template = [
    // ── File ──────────────────────────────────────────────────
    {
      label: '&File',
      submenu: [
        {
          label: '&New Scheme',
          accelerator: 'CmdOrCtrl+N',
          click: () => navigate('/upload'),
        },
        {
          label: '&Open Scheme',
          accelerator: 'CmdOrCtrl+O',
          click: () => navigate('/dashboard'),
        },
        { type: 'separator' },
        {
          label: '&Save Lesson',
          accelerator: 'CmdOrCtrl+S',
          click: () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('menu:save');
            }
          },
        },
        {
          label: '&Print Lesson…',
          accelerator: 'CmdOrCtrl+P',
          click: () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.print();
            }
          },
        },
        { type: 'separator' },
        {
          label: '&Sign Out',
          click: () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('menu:sign-out');
            }
          },
        },
        { type: 'separator' },
        isMac ? { role: 'close', label: '&Close' } : { role: 'quit', label: '&Exit' },
      ],
    },
    // ── Edit ──────────────────────────────────────────────────
    {
      label: '&Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    // ── View ──────────────────────────────────────────────────
    {
      label: '&View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        { type: 'separator' },
        {
          label: '&Backend Status',
          click: () => {
            if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('menu:backend-status');
            }
          },
        },
      ],
    },
    // ── Help ──────────────────────────────────────────────────
    {
      label: '&Help',
      role: 'help',
      submenu: [
        {
          label: '&Documentation',
          click: () => {
            const docsPath = path.join(getBackendDir(), '..', 'docs');
            if (fs.existsSync(docsPath)) {
              shell.openPath(docsPath);
            } else if (mainWindow && !mainWindow.isDestroyed()) {
              mainWindow.webContents.send('menu:navigate', '/');
            }
          },
        },
        {
          label: '&Keyboard Shortcuts',
          click: () => {
            showShortcutsDialog();
          },
        },
        { type: 'separator' },
        {
          label: '&Report a Problem',
          click: () => {
            const logFile = path.join(appDataPath, 'diagnostics.log');
            if (fs.existsSync(logFile)) {
              shell.showItemInFolder(logFile);
            } else {
              dialog.showMessageBox(mainWindow, {
                type: 'info',
                title: 'SchemeKnit',
                message: 'No diagnostics log yet',
                detail: 'The diagnostics log is created after the app has run once.',
              });
            }
          },
        },
        { type: 'separator' },
        {
          label: '&About SchemeKnit',
          click: () => {
            showAboutDialog();
          },
        },
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}

function showAboutDialog() {
  const version = app.getVersion();
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: 'About SchemeKnit',
    message: 'SchemeKnit Desktop',
    detail: [
      'Version: ' + version,
      'Electron: ' + process.versions.electron,
      'Node: ' + process.versions.node,
      'Chromium: ' + process.versions.chrome,
      'Platform: ' + process.platform + ' (' + process.arch + ')',
      '',
      'Local evaluation build - runs entirely on this PC.',
      '',
      'BloomCore Technologies',
    ].join('\n'),
    buttons: ['OK'],
  });
}

function showShortcutsDialog() {
  dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: 'Keyboard Shortcuts',
    message: 'SchemeKnit Keyboard Shortcuts',
    detail: [
      'File',
      '  Ctrl+N   New Scheme',
      '  Ctrl+O   Open Scheme',
      '  Ctrl+S   Save Lesson',
      '  Ctrl+P   Print Lesson',
      '',
      'Edit',
      '  Ctrl+Z   Undo',
      '  Ctrl+Shift+Z   Redo',
      '  Ctrl+X / C / V   Cut / Copy / Paste',
      '  Ctrl+A   Select All',
      '',
      'View',
      '  Ctrl+R   Reload',
      '  Ctrl+Shift+R   Force Reload',
      '  Ctrl+= / -   Zoom In / Out',
      '  Ctrl+0   Reset Zoom',
      '  F11   Fullscreen',
      '',
      'Application',
      '  Alt+F4   Exit (Windows)',
    ].join('\n'),
    buttons: ['OK'],
  });
}

// ============================================================
// IPC HANDLERS
// ============================================================

ipcMain.handle('get-app-info', () => ({
  version: app.getVersion(),
  isDev,
  userDataPath,
  appDataPath,
  dbPath,
  uploadsPath,
  exportsPath,
}));

ipcMain.handle('get-backend-status', () => ({
  ready: backendReady,
  port: BACKEND_PORT,
}));

ipcMain.handle('restart-backend', async () => {
  stopBackend();
  startBackend();
  try {
    await waitForBackend();
    notifyFrontendReady();
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle('save-file', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    title: 'Save File',
    ...options,
  });
  return result;
});

ipcMain.handle('open-folder', async (event, folderPath) => {
  await shell.openPath(folderPath);
});

// ============================================================
// APP LIFECYCLE
// ============================================================

// Single instance lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    diagLog('=== SchemeKnit Desktop Starting ===');
    diagLog('Electron version: ' + process.versions.electron);
    diagLog('Node version: ' + process.versions.node);
    diagLog('platform: ' + process.platform);
    diagLog('arch: ' + process.arch);
    diagLog('process.execPath: ' + process.execPath);
    diagLog('userDataPath: ' + userDataPath);

    ensureDirectories();

    // Start frontend HTTP server first
    try {
      frontendServer = await createFrontendServer();
    } catch (err) {
      diagLog('Failed to start frontend server: ' + err.message);
      dialog.showMessageBox({
        type: 'error',
        title: 'SchemeKnit - Startup Error',
        message: 'SchemeKnit could not start its local web server.',
        detail: err.message,
        buttons: ['Close'],
      }).then(() => { app.quit(); });
      return;
    }

    // Create window and load frontend via HTTP
    createWindow();

    // Set native application menu
    Menu.setApplicationMenu(buildAppMenu());

    // Start backend
    startBackend();

    // Wait for backend, then notify frontend
    try {
      await waitForBackend();
      notifyFrontendReady();
    } catch (err) {
      diagLog('Backend startup failed: ' + err.message);
      showBackendError(err.message);
    }
  });

  app.on('window-all-closed', () => {
    stopFrontendServer();
    stopBackend();
    app.quit();
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });

  app.on('before-quit', () => {
    stopFrontendServer();
    stopBackend();
  });
}
