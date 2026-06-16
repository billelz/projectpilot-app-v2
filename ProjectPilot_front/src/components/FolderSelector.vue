<script>
import { useProjectStore } from '../stores/projectStore'
export default {
  setup() {
    const store = useProjectStore()
    return { store }
  },
  data() {
    return {
      selectedFolder: null,
      showError: false,
    };
  },
  methods: {
    async selectFolder() {
      try {
        const folderPath = await window.ipcRenderer.invoke('select-folder');
        if (folderPath) { 
          this.selectedFolder = folderPath;
          this.store.setSelectedFolder(folderPath);
          this.showError = false;
          this.store.setStatus("IMPORTING")
        } 
      } catch (error) {
        console.error('Error selecting folder:', error);
      }
    },
    async runProject() {
      if (!this.selectedFolder) {
        this.showError = true;
        return;
      }
      this.showError = false;
      try {
        const response = await window.ipcRenderer.invoke(
          'analyze-project',
          this.selectedFolder
        );
        this.store.setAnalysisResult(response);
      } catch (error) {
        this.store.setError(error.message);
      }
    },
   stopProject() {
  const stopCommand =
    this.store.analysisResult?.install?.result?.stop_command;
  if (stopCommand) {
    window.ipcRenderer.send('run-stop-command', stopCommand);
  } else {
    window.ipcRenderer.send('run-stop-command', null);
  }
  this.store.setStatus('idle');
},
    // Returns 'completed' | 'active' | 'pending' for a given step number (1-4),
    // based on how far along the overall status order we are.
    // isLast: the final step has no "in progress" state of its own —
    // reaching it means everything is done.
    stepState(stepIndex, isLast = false) {
      if (isLast) {
        return this.currentStepIndex >= stepIndex ? 'completed' : 'pending';
      }
      if (this.currentStepIndex > stepIndex) return 'completed';
      if (this.currentStepIndex === stepIndex) return 'active';
      return 'pending';
    }
  },
  computed: {
    isRunning() {
      const status = (this.store.projectStatus || '').toLowerCase();
      return status === 'done';
    },
    // Order of statuses, lowercase, so comparisons are case-insensitive
    // regardless of how setStatus() was called ('IMPORTING' vs 'running' etc.)
    currentStepIndex() {
      const order = ['idle', 'importing', 'setting', 'running', 'done'];
      const status = (this.store.projectStatus || '').toLowerCase();
      const idx = order.indexOf(status);
      return idx === -1 ? 0 : idx;
    }
  }
};
</script>

<template>
  <div class="selector-container">
    <label class="selector-label">Select Project</label>
    <div v-if="showError" class="error-message">
      Choose a project folder
    </div>
    <div class="folder_selector">
      <input 
      :value="selectedFolder || null"
        placeholder="Project Folder Path" 
        type="text" 
        name="text" 
        disabled 
        class="input"
        :class="{ 'input-error': showError }"
      >
      <button class="btn-action" @click="selectFolder" :disabled="isRunning">Browse</button>
      <button
        class="btn-action"
        @click="runProject"
        :disabled="isRunning"
      >
        <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="currentColor">
          <path d="M320-200v-560l440 280-440 280Zm80-280Zm0 134 210-134-210-134v268Z"/>
        </svg>
        <span>Run project</span>
      </button>
    </div>
<div class="stepper_stop_container">
  <div class="stepper-content-wrapper">
    <div class="stepper-wrapper">
      <div class="stepper-item">
        <div :class="['stepper-circle', 'stepper-' + stepState(1)]">
          <div v-if="stepState(1) === 'completed'">
            <svg viewBox="0 0 16 16" fill="currentColor" height="16" width="16" xmlns="http://www.w3.org/2000/svg">
            <path d="M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425z"></path>
            </svg>
          </div>
          <div v-else>
              1
          </div>
        </div>
        <div class="stepper-label">Importing</div>
        <div :class="['stepper-line', { completed: stepState(1) === 'completed' }]"></div>
      </div>

      <div class="stepper-item">
        <div :class="['stepper-circle', 'stepper-' + stepState(2)]">
          <div v-if="stepState(2) === 'completed'">
            <svg viewBox="0 0 16 16" fill="currentColor" height="16" width="16" xmlns="http://www.w3.org/2000/svg">
              <path d="M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425z"></path>
            </svg>
          </div>
          <div v-else>
              2
          </div>
        </div>
        <div class="stepper-label">Setting up tools</div>
        <div :class="['stepper-line', { completed: stepState(2) === 'completed' }]"></div>
      </div>

      <div class="stepper-item">
        <div :class="['stepper-circle', 'stepper-' + stepState(3)]">
          <div v-if="stepState(3) === 'completed'">
            <svg viewBox="0 0 16 16" fill="currentColor" height="16" width="16" xmlns="http://www.w3.org/2000/svg">
              <path d="M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425z"></path>
            </svg>
          </div>
          <div v-else>
              3
          </div>
        </div>
        <div class="stepper-label">Running</div>
        <div :class="['stepper-line', { completed: stepState(3) === 'completed' }]"></div>
      </div>

      <div class="stepper-item">
        <div :class="['stepper-circle', 'stepper-' + stepState(4, true)]">
          <div v-if="stepState(4, true) === 'completed'">
            <svg viewBox="0 0 16 16" fill="currentColor" height="16" width="16" xmlns="http://www.w3.org/2000/svg">
              <path d="M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425z"></path>
            </svg>
          </div>
          <div v-else>
              4
          </div>
        </div>
        <div class="stepper-label">Runned</div>
      </div>
    </div>
    <button
      class="btn-stop"
      :class="{ 'btn-stop-active': isRunning }"
      @click="stopProject"
      :disabled="!isRunning"
    >
      <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="currentColor">
        <path d="M320-320h320v-320H320v320ZM480-80q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Zm0-80q134 0 227-93t93-227q0-134-93-227t-227-93q-134 0-227 93t-93 227q0 134 93 227t227 93Zm0-320Z"/>
      </svg>
      <span>Stop Project</span>
    </button>
  </div>
</div>
  </div>
</template>

<style scoped>
.selector-container {
  display: flex;
  flex-direction: column;
  gap: 25px;
  width: 100%;
}

.selector-label {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
}

.folder_selector {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.input {
  flex: 1;
  min-width: 200px;
  height: 45px;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1.5px solid #ddd;
  outline: none;
  font-size: 14px;
  font-family: inherit;
  transition: all 0.3s ease;
}

.input:focus {
  border-color: #1570EF;
  box-shadow: 0 0 0 3px rgba(21, 112, 239, 0.1);
}

.btn-action {
  font-family: inherit;
  font-size: 15px;
  background: #1570EF;
  color: white;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: none;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s ease;
  justify-content: center;
  cursor: pointer;
  white-space: nowrap;
  min-width: 140px;
  height: 45px;
}

.btn-action:hover {
  background: #0d5cc4;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(21, 112, 239, 0.3);
}

.btn-action:active {
  transform: translateY(0);
}

.btn-action:disabled {
  background: #a0c4f1;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
  opacity: 0.7;
}

.btn-action:disabled:hover {
  background: #a0c4f1;
  transform: none;
  box-shadow: none;
}
.stepper_stop_container {
  width: 100%;
  margin-top: 15px;
}
.stepper-content-wrapper {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  justify-content: space-between;
}
.stepper-wrapper {
  display: flex;
  align-items: flex-start;
  gap: 0;
  flex: 1;
  position: relative;
}
.stepper-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  position: relative;
}

.stepper-circle {
  width: 35px;
  height: 35px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
  font-weight: bold;
  font-size: 14px;
  z-index: 3;
  position: relative;
  flex-shrink: 0;
}

.stepper-circle.stepper-completed {
  background-color: #0084ff;
  color: white;
}

.stepper-circle.stepper-active {
  background-color: #ff9800;
  color: white;
  border: 2px solid white;
  box-shadow: 0 0 0 2px #ff9800;
}

.stepper-circle.stepper-pending {
  background-color: #e8e8e8;
  color: #999;
  border: 2px solid #d3d3d3;
}

.stepper-label {
  font-size: 11px;
  text-align: center;
  color: #666;
  font-weight: 500;
  width: 100%;
  word-wrap: break-word;
  padding: 0 5px;
}

.stepper-line {
  position: absolute;
  top: 17px;
  left: 50%;
  width: 100%;
  height: 2px;
  background-color: #d3d3d3;
  z-index: 1;
}

.stepper-line.completed {
  background-color: #0084ff;
}

.btn-stop {
  font-family: inherit;
  font-size: 14px;
  background: #e8e8e8;
  color: #999;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #d3d3d3;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s ease;
  cursor: not-allowed;
  white-space: nowrap;
  flex-shrink: 0;
}

.btn-stop-active {
  background: #ef4444;
  color: white;
  border-color: #ef4444;
  cursor: pointer;
}

.btn-stop-active:hover {
  background: #dc2626;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
}

.btn-stop:disabled:hover {
  background: #e8e8e8;
  transform: none;
  box-shadow: none;
}

.btn-stop svg {
  width: 18px;
  height: 18px;
}

svg {
  width: 20px;
  height: 20px;
}
.error-message {
  color: #dc3545;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: -17px;
  margin-top: -17px;
  animation: slideInError 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes slideInError {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.input-error {
  border-color: #dc3545 !important;
  border-width: 2px !important;
  box-shadow: 0 0 0 1px rgba(220, 53, 69, 0.15) !important;
}
</style>