<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores'

const route = useRoute()
const authStore = useAuthStore()

const redirectPath = computed(() => {
  const r = route.query.redirect as string | undefined
  return r && r.startsWith('/') ? r : '/dashboard'
})

function handleLogin() {
  authStore.loginWithKeycloak(redirectPath.value)
}
</script>

<template>
  <div class="term-auth-page">
    <div class="term-auth-container">
      <div class="term-auth-header">
        <img src="/icon.svg" alt="" style="height: 3rem; margin-bottom: 1rem;">
        <h1>WolfpackCloud</h1>
        <p>Control · Вход через Keycloak</p>
      </div>

      <div class="term-card" style="padding: 1.5rem;">
        <div v-if="authStore.error" class="term-alert term-alert-error">
          {{ authStore.error }}
        </div>

        <p class="term-text-dim term-mb-1">
          Откроется страница входа Keycloak на поддомене <strong>auth</strong>.
        </p>

        <button
          type="button"
          class="term-btn term-btn-primary"
          style="width: 100%;"
          @click="handleLogin"
        >
          Войти через Keycloak
        </button>

        <p class="term-text-dim term-mt-1 term-fs-2xs">
          После входа вы вернётесь на {{ redirectPath }}
        </p>
      </div>
    </div>

    <footer class="term-footer" style="position: fixed; bottom: 0; left: 0; right: 0;">
      WolfpackCloud — control
    </footer>
  </div>
</template>
