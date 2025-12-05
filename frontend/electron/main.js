const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

// 保持对 window 对象的全局引用，避免 JavaScript 对象被垃圾回收时窗口关闭。
let mainWindow;
let backendProcess;

// IPC handler for opening directory dialog
ipcMain.handle('dialog:openDirectory', async () => {
  console.log('IPC: dialog:openDirectory triggered');
  const { canceled, filePaths } = await dialog.showOpenDialog({
    properties: ['openDirectory'],
  });
  if (canceled) {
    console.log('IPC: Dialog canceled');
    return null;
  } else {
    console.log('IPC: Selected path:', filePaths[0]);
    return filePaths[0];
  }
});

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, 
    },
  });

  const startUrl = process.env.ELECTRON_START_URL || 'http://localhost:5173';
  mainWindow.loadURL(startUrl);

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

function startBackend() {
  // 简单启动后端逻辑：假设 Python 在环境变量中
  // 在实际打包中，可能需要打包这一部分或者指向打包后的 executable
  const backendPath = path.join(__dirname, '../../backend/app/main.py');
  
  console.log('Starting backend from:', backendPath);
  
  // 使用 uvicorn 启动
  // 注意：这里假设用户环境里 python/uvicorn 是可用的
  // 生产环境通常会把后端打包成一个 .exe
  backendProcess = spawn('python', ['-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'], {
      cwd: path.join(__dirname, '../../') // 设置工作目录为项目根目录
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`Backend stdout: ${data}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`Backend stderr: ${data}`);
  });
}

app.on('ready', () => {
    // 暂时手动启动后端，或者可以在这里自动启动
    // startBackend(); 
    createWindow();
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
  // 杀掉后端进程
  if (backendProcess) {
      backendProcess.kill();
  }
});

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});
