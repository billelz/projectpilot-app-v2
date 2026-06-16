import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { useProjectStore } from './stores/projectStore'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

const store = useProjectStore()
window.ipcRenderer.on('status-update', (_event, status) => {
  store.setStatus(status)
})

app.mount('#app')