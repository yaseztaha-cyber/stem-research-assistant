const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const PORT = 8765;
const isDev = !app.isPackaged;

let mainWindow = null;
let pythonProcess = null;

function getPythonPath() {
  if (isDev) {
    return 'python';
  }
  const resourcesPath = process.resourcesPath;
  const pythonPath = path.join(resourcesPath, 'backend', 'python', 'python.exe');
  if (fs.existsSync(pythonPath)) return pythonPath;
  return path.join(resourcesPath, 'backend', 'venv', 'Scripts', 'python.exe');
}

function getBackendPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'backend');
  }
  return path.join(process.resourcesPath, 'backend');
}

function waitForServer(url, maxAttempts = 60) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      http.get(url, (res) => {
        if (res.statusCode === 200) resolve();
        else retry();
      }).on('error', retry);
    };
    const retry = () => {
      attempts++;
      if (attempts >= maxAttempts) reject(new Error('Backend failed to start'));
      else setTimeout(check, 500);
    };
    check();
  });
}

function startPythonBackend() {
  const pythonPath = getPythonPath();
  const backendPath = getBackendPath();
  const modulePath = path.join(backendPath, 'app', 'main.py');

  const args = [
    '-m', 'uvicorn',
    'app.main:app',
    '--host', '127.0.0.1',
    '--port', String(PORT),
    '--app-dir', backendPath
  ];

  pythonProcess = spawn(pythonPath, args, {
    cwd: backendPath,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python ERR] ${data.toString().trim()}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'STEM Research Assistant',
    icon: path.join(__dirname, 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    show: false
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  const frontendPath = isDev
    ? 'http://localhost:5173'
    : `file://${path.join(__dirname, '..', 'frontend', 'dist', 'index.html')}`;

  mainWindow.loadURL(frontendPath);
}

app.whenReady().then(async () => {
  try {
    startPythonBackend();
    await waitForServer(`http://127.0.0.1:${PORT}/api/health`);
    console.log('Backend ready');
  } catch (err) {
    dialog.showErrorBox('Startup Error', `Failed to start backend: ${err.message}`);
    app.quit();
    return;
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
});

ipcMain.handle('get-backend-url', () => `http://127.0.0.1:${PORT}`);
