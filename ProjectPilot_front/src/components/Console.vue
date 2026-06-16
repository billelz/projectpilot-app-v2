<script>
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useProjectStore } from '@/stores/projectStore'  
import { FitAddon } from '@xterm/addon-fit';
export default {
  name: 'Console',
  setup() { 
    const store = useProjectStore()
    return { store }
  },
  data() {
    return {
      terminal: null,
      fitAddon: null,
      resizeObserver: null,
      showCommandModal: false,      
      pendingCommand: '',           
      commandsQueue: [],            
      currentCommandIndex: 0,
      storedError: null,
      websocket: null,
    };
  },
  watch: {  
    'store.analysisResult'(newResult) {
      if (newResult) {
        this.displayAnalysisResult(newResult)
      }
    },
    'store.lastError'(newError) {
      if (newError) {
        this.displayError(newError)
      }
    }
  },
  mounted() {
    this.initializeTerminal();
    this.initWebSocket();
    window.ipcRenderer.on('command-done', this.onCommandDone);
    window.ipcRenderer.on('automation-error', this.onAutomationError); 
  },
  beforeUnmount() {
    try {
      if (this.resizeObserver) {
        this.resizeObserver.disconnect();
        this.resizeObserver = null;
      }
      if (this.terminal) {
        this.terminal.dispose();
        this.terminal = null;
      }
      if (this.websocket) {
        this.websocket.close();
        this.websocket = null;
      }
      if (window.ipcRenderer && typeof window.ipcRenderer.removeListener === 'function') {
        window.ipcRenderer.removeListener('command-done', this.onCommandDone)
        window.ipcRenderer.removeListener('automation-error', this.onAutomationError);
      }
    } catch (e) {
      console.error("Error during Console unmount:", e)
    }
  },
  
  methods: {
initWebSocket() {
  try {
    this.websocket = new WebSocket('ws://127.0.0.1:8000/ws');
    
    this.websocket.onopen = () => {
      console.log('WebSocket connected to backend');
    };
    
    this.websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Received from backend:', data);
        
        if (data.type === 'fix') {
          this.displayErrorFix(data);
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };
    this.websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.terminal?.writeln(`\x1b[31m[WebSocket Error]\x1b[0m Connection failed`);
    };
    this.websocket.onclose = () => {
      console.log('WebSocket disconnected');
    };
  } catch (error) {
    console.error('Failed to initialize WebSocket:', error);
  }
},
fitAndResize() {
  if (!this.terminal || !this.fitAddon) return;
  this.fitAddon.fit();
  window.ipcRenderer.send('terminal:resize', {
    cols: this.terminal.cols,
    rows: this.terminal.rows,
  });
},
onCommandDone() {
  this.currentCommandIndex++;
  this.showNextCommand();
},
onAutomationError(event, { exitCode, signal, errorOutput }) {
    this.showCommandModal = false;
     this.commandsQueue = [];
     this.storedError = { 
    exitCode, 
    signal, 
    command: this.pendingCommand,
    errorOutput: errorOutput || '',
  };  
  this.sendErrorToBackend(exitCode, errorOutput);
  },

sendErrorToBackend(exitCode, errorOutput = '') {
  if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
    console.warn('WebSocket not connected');
    this.terminal?.writeln(`\x1b[33m[Warning]\x1b[0m WebSocket not connected`);
    return;
  }
  
  this.terminal?.writeln('');
  this.terminal?.writeln(`\x1b[33m[Analyzing Error]\x1b[0m Sending to AI for analysis...`);
  
  const errorMessage = {
    type: 'error',
    command: this.pendingCommand,
    exitCode: exitCode,
    projectPath: this.store.selectedFolder || '',
    errorOutput: errorOutput,  // Include error output
  };
  this.websocket.send(JSON.stringify(errorMessage));
  console.log('Error sent to backend:', errorMessage);
},

displayErrorFix(data) {
  const fix = data.result;

  if (
    fix.alternative_commands &&
    Array.isArray(fix.alternative_commands) &&
    fix.alternative_commands.length > 0
  ) {
    this.commandsQueue = fix.alternative_commands;
    this.currentCommandIndex = 0;

    setTimeout(() => {
      this.showNextCommand();
    }, 300);
  }
},

  initializeTerminal() {
  if (this.terminal) return;
  const theme = {
    background: '#050A24',
    foreground: '#ffffff',
    cursor: '#4a90e2',
  };
  this.terminal = new Terminal({
    cursorBlink: true,
    cursorStyle: 'bar',
    fontFamily: "'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace",
    fontSize: 13,
    theme,
    convertEol: true,
  });
  this.fitAddon = new FitAddon();
  this.terminal.loadAddon(this.fitAddon);
  this.terminal.open(this.$refs.terminalContainer);
  this.terminal.focus();
  this.onTerminalData = (event, data) => {
    this.terminal?.write(data);
  };
  window.ipcRenderer.on('terminal:data', this.onTerminalData);
  this.terminal.onData((data) => {
    window.ipcRenderer.send('terminal:input', data);
  });
  requestAnimationFrame(() => this.fitAndResize());
  this.resizeObserver = new ResizeObserver(() => this.fitAndResize());
  this.resizeObserver.observe(this.$refs.terminalContainer);
},
displayAnalysisResult(response) {
  if (this.terminal) {
    if (typeof response === 'object') {  
      let commands = null;      
      if (response.commands && Array.isArray(response.commands)) {
        commands = response.commands;
      } 
      else if (response.install?.result?.commands && Array.isArray(response.install.result.commands)) {
        commands = response.install.result.commands;
      }      
      if (commands) {
        this.store.setStatus("SETTING")
        this.commandsQueue = commands;
        this.currentCommandIndex = 0;
        setTimeout(() => this.showNextCommand(), 500);
      }
    } else if (response.install_guide) {
      this.terminal.writeln(response.install_guide);
    } else {
      this.terminal.writeln(String(response));
    }
    this.terminal.writeln('');
  }
},
showNextCommand() {
  if (this.currentCommandIndex < this.commandsQueue.length) {
    this.pendingCommand = this.commandsQueue[this.currentCommandIndex];
    this.showCommandModal = true;
  }
},
handleCommandConfirm() {
  this.showCommandModal = false;
  const i = 1;
  if ( i == 1) {
    this.store.setStatus("running")  
  }
  window.ipcRenderer.send('execute-command', this.pendingCommand, this.store.selectedFolder);
},
handleCommandDeny() {
  this.store.setStatus("idle")  
  this.terminal.writeln(`\x1b[31m✗ Permission Denied:\x1b[0m ${this.pendingCommand}`);
  this.terminal.writeln('');
  this.showCommandModal = false;
  this.commandsQueue = [];
  this.currentCommandIndex = 0;
  window.ipcRenderer.send('terminal:show-prompt');

},
displayError(error) {
      if (this.terminal) {
        this.terminal.writeln('');
        this.terminal.writeln(`\x1b[31m[Error]\x1b[0m ${error}`);
        this.terminal.writeln('');
      }
    }
  }
};
</script>
<template>
  <div v-if="showCommandModal" class="modal-overlay">
    <div class="modal-dialog">
      <h2>Accept to run this command?</h2>
      <p>{{ pendingCommand }}</p>
      <div class="modal-buttons">
        <button @click="handleCommandDeny">Decline & Exit</button>
        <button @click="handleCommandConfirm">Yes</button>
      </div>
    </div>
  </div>
  <div class="console-wrapper">
    <div ref="terminalContainer" class="terminal-container"></div>
  </div>
</template>

<style scoped>
.console-wrapper {
  width: 100%;
  height: 100%;
  background: #050A24;
  border: 1px solid #0d6e8f;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}

.terminal-container {
  width: 100%;
  height: 100%;
}
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.modal-dialog {
  background: white;
  padding: 1.5rem;
  border-radius: 0.5rem;
  box-shadow: 0 20px 25px rgba(0, 0, 0, 0.1);
  max-width: 28rem;
  width: 90%;
}

.modal-dialog h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: bold;
  color: #111827;
}

.modal-dialog p {
  margin: 1rem 0 0 0;
  font-size: 0.875rem;
  color: #4b5563;
  font-family: monospace;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.modal-buttons {
  margin-top: 1.5rem;
  display: flex;
  gap: 1rem;
}

.modal-buttons button {
  flex: 1;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.modal-buttons button:first-child {
  background-color: #d1d5db;
  color: #111827;
}

.modal-buttons button:first-child:hover {
  background-color: #9ca3af;
}

.modal-buttons button:last-child {
  background-color: #000000;
  color: white;
}

.modal-buttons button:last-child:hover {
  background-color: #1f2937;
}
</style>