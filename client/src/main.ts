import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './style.css'
import { initKeycloak, keycloak } from './keycloak'

const app = createApp(App)
app.use(createPinia())

async function bootstrap() {
  await initKeycloak()

  if (!import.meta.env.VITE_KEYCLOAK_URL) {
    console.error('Set VITE_KEYCLOAK_URL for OIDC')
  }

  app.use(router)
  app.mount('#app')

  keycloak.onTokenExpired = () => {
    keycloak.updateToken(30).catch(() => keycloak.login())
  }
}

bootstrap()
