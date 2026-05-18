import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

import { authApi } from '@/api'
import { keycloak } from '@/keycloak'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => keycloak.authenticated && !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function fetchUser() {
    loading.value = true
    error.value = null
    try {
      if (!keycloak.authenticated || !keycloak.token) {
        user.value = null
        return
      }
      user.value = await authApi.getMe()
    } catch (e: unknown) {
      user.value = null
      const err = e as { response?: { data?: { detail?: string } } }
      error.value = err.response?.data?.detail || 'Не удалось загрузить профиль'
    } finally {
      loading.value = false
    }
  }

  /** Редирект на Keycloak; после входа пользователь вернётся на redirectUri. */
  function loginWithKeycloak(redirectPath = '/dashboard') {
    error.value = null
    let path = redirectPath.startsWith('/') ? redirectPath : '/dashboard'
    const i = path.indexOf('#')
    if (i !== -1) path = path.slice(0, i)
    keycloak.login({ redirectUri: `${window.location.origin}${path}` })
  }

  function logout() {
    user.value = null
    keycloak.logout({ redirectUri: `${window.location.origin}/login` })
  }

  async function init() {
    if (!keycloak.authenticated) {
      user.value = null
      return
    }
    await fetchUser()
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    isAdmin,
    fetchUser,
    loginWithKeycloak,
    logout,
    init,
  }
})
