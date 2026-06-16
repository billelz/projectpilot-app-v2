import { app, BrowserWindow,Menu,ipcMain, dialog, } from 'electron'
import os from 'os'
import * as pty from 'node-pty'
import { execFile, spawn, ChildProcess } from 'child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬─┬ dist
// │ │ └── index.html
// │ │
// │ ├─┬ dist-electron
// │ │ ├── main.js
// │ │ └── preload.mjs
// │
process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

let win: BrowserWindow | null
let ptyProcess: pty.IPty | null = null;
let backendProcess: ChildProcess | null = null;
let jobPty: pty.IPty | null = null;
const containerIdRegex = /^[a-f0-9]{12,64}$/;
function startBackend() {
  const isPackaged = app.isPackaged;

  let backendExecutable: string;
  let backendArgs: string[] = [];
  let backendCwd: string;

  if (isPackaged) {
    // In production: look for the bundled backend binary in resources/
    const platform = os.platform();
    const binaryName = platform === 'win32' ? 'projectpilot-backend.exe' : 'projectpilot-backend';
    backendExecutable = path.join(process.resourcesPath, 'backend', binaryName);
    backendCwd = path.join(process.resourcesPath, 'backend');
  } else {
    // In development: use the venv Python so uvicorn and deps are available
    backendCwd = path.join(process.env.APP_ROOT!, '..', 'ProjectPilot');
    const isWin = os.platform() === 'win32';
    const venvPython = isWin
      ? path.join(backendCwd, '.venv', 'Scripts', 'python.exe')
      : path.join(backendCwd, '.venv', 'bin', 'python3');
    backendExecutable = venvPython;
    backendArgs = ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000'];
  }

  backendProcess = spawn(backendExecutable, backendArgs, {
    cwd: backendCwd,
    stdio: 'pipe',
    env: { ...process.env },
  });

  backendProcess.stdout?.on('data', (data) => {
    console.log('[backend]', data.toString().trim());
  });

  backendProcess.stderr?.on('data', (data) => {
    console.error('[backend error]', data.toString().trim());
  });

  backendProcess.on('exit', (code) => {
    console.log('[backend] exited with code', code);
    backendProcess = null;
  });
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
}

// Poll /health until the backend is up (max 30 s)
function waitForBackend(retries = 60, delayMs = 500): Promise<void> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      fetch('http://127.0.0.1:8000/health')
        .then(r => r.ok ? resolve() : retry())
        .catch(() => retry());
    };
    const retry = () => {
      attempts++;
      if (attempts >= retries) return reject(new Error('Backend did not start in time'));
      setTimeout(check, delayMs);
    };
    check();
  });
}
function createWindow() {
  win = new BrowserWindow({
    width: 1400,        
    height: 800,        
    minWidth: 1400,      
    minHeight: 800,
    show: false,       
    icon: path.join(process.env.VITE_PUBLIC, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
    },
  })

  Menu.setApplicationMenu(null)
  win.webContents.on('did-finish-load', () => {
    win?.show()  
    win?.maximize()
    win?.webContents.send('main-process-message', (new Date).toLocaleString())
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
  
  createPTY()

}


ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
    title: 'Select Project Folder',
    buttonLabel: 'Select',
  })
  return result.filePaths[0] || null
})
ipcMain.handle('get-user-info', () => {
  const userInfo = os.userInfo();
  const hostname = os.hostname();
  const shell = process.env.SHELL || process.env.ComSpec || '/bin/bash';
  
  return {
    username: userInfo.username,
    homePath: userInfo.homedir,
    hostname: hostname,
    shell: shell,
  };
});
ipcMain.on('terminal:input', (_event, data) => {
  ptyProcess?.write(data)
})
ipcMain.on('terminal:resize', (_event, size) => {
  if (!ptyProcess) return;
  const cols = Math.max(2, Number(size?.cols) || 80);
  const rows = Math.max(1, Number(size?.rows) || 24);
  ptyProcess.resize(cols, rows);
});

// Helper function to get clean stderr for error reporting
const getCommandStderr = (command: string, cwd: string): Promise<string> => {
  return new Promise((resolve) => {
    const shell = os.platform() === 'win32' ? 'powershell.exe' : 'bash';
    const args = os.platform() === 'win32' ? ['-Command', command] : ['-c', command];
    
    let stderrData = '';
    
    execFile(shell, args, {
      cwd: cwd,
      maxBuffer: 1024 * 1024,  // 1MB buffer
      timeout: 60000,  // 60 second timeout
    }, (error, _stdout, stderr) => {
      stderrData = stderr || error?.message || '';
      resolve(stderrData.trim());
    });
  });
};
ipcMain.on('execute-command', (_event, command, projectPath) => {
  if (!command?.trim()) return;

  const cwd = projectPath || os.homedir();

    jobPty = pty.spawn(
    os.platform() === 'win32' ? 'powershell.exe' : 'bash',
    os.platform() === 'win32' ? ['-Command', command] : ['-c', command],
    {
      name: 'xterm-color',
      cols: 80,
      rows: 30,
      cwd: cwd,
      env: process.env as NodeJS.ProcessEnv
    }
  );
  
  jobPty.onData((data) => {
    win?.webContents.send('terminal:data', data);
      if (data.includes("Started")){
        win?.webContents.send('status-update', 'done');
      }
      if (containerIdRegex.test(data.trim()) && !data.includes("Error")) {
        win?.webContents.send('status-update', 'done');
      }
      if (data.includes("http://localhost:")) {
        win?.webContents.send('status-update', 'done');
      }
  });
  
  jobPty.onExit(async ({ exitCode, signal }) => {
  if (exitCode !== 0) {
    const errorOutput = await getCommandStderr(command, cwd);
    
    win?.webContents.send('automation-error', { 
      exitCode, 
      signal,
      errorOutput: errorOutput || 'Command failed with exit code ' + exitCode
    });
  } else {
    win?.webContents.send('command-done');
  }

  jobPty?.kill();
  ptyProcess?.write('\r'); 
});
}); 
ipcMain.on('run-stop-command', (_event, stopCommand) => {
  if (stopCommand && typeof stopCommand === 'string') {
    ptyProcess?.write(stopCommand + '\r');
    return;
  }
  if (jobPty) {
    jobPty.kill();
    jobPty = null;
  }
});
ipcMain.on('terminal:show-prompt', () => {
  ptyProcess?.write('\r');
});

function createPTY() {
  const shell = os.platform() === 'win32'
    ? 'powershell.exe'
    : 'bash';
  ptyProcess = pty.spawn(shell, [], {
    name: 'xterm-color',
    cols: 80,
    rows: 30,
    cwd: os.homedir(),
    env: process.env as NodeJS.ProcessEnv
  });
  ptyProcess.onData((data) => {
    win?.webContents.send('terminal:data', data);
  }); 
}
// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopBackend()
    app.quit()
    win = null
  }
})

app.on('before-quit', () => {
  stopBackend()
})

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.whenReady().then(() => {
  startBackend()
  waitForBackend().catch(err => console.error('[backend]', err.message))
  createWindow()
})

ipcMain.handle('analyze-project', async (_event, path: string) => {
  await waitForBackend(60, 500).catch(() => {
    throw new Error('Backend is not reachable. Please restart the app.')
  })

  const response = await fetch('http://127.0.0.1:8000/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`)
  }

  return response.json()
})