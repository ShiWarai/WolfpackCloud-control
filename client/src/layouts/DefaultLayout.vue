<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores'

const route = useRoute()
const authStore = useAuthStore()

const user = computed(() => authStore.user)
const isAdmin = computed(() => authStore.isAdmin)

const sidebarExpanded = ref(false)

onMounted(() => {
  const saved = localStorage.getItem('wpc-monitoring-sidebar-expanded')
  if (saved === '1') {
    sidebarExpanded.value = true
  }
})

function toggleSidebar() {
  sidebarExpanded.value = !sidebarExpanded.value
  localStorage.setItem('wpc-monitoring-sidebar-expanded', sidebarExpanded.value ? '1' : '0')
}

function handleLogout() {
  authStore.logout()
}

function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(path + '/')
}
</script>

<template>
  <div class="term-page has-sidebar" :class="{ 'sidebar-expanded': sidebarExpanded }">
    <div class="term-header-logo-cell">
      <RouterLink to="/dashboard" class="term-brand">
        <img src="/icon.svg" alt="">
        <span>Control</span>
      </RouterLink>
    </div>
    
    <header class="term-header">
      <div class="term-brand-wrap">
        <span class="term-text-dim" v-if="!sidebarExpanded">WolfpackCloud Control</span>
      </div>
      <nav class="term-nav" aria-label="Верхнее меню">
        <RouterLink 
          to="/dashboard" 
          class="term-nav-icon" 
          :class="{ 'term-active': isActive('/dashboard') }"
          title="Dashboard"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
        </RouterLink>
        <a 
          v-if="user"
          href="#" 
          @click.prevent="handleLogout"
          class="term-nav-icon" 
          title="Выход"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </a>
      </nav>
    </header>
    
    <div class="term-app-layout">
      <div class="term-sidebar-wrap">
        <button 
          type="button" 
          class="term-sidebar-toggle" 
          @click="toggleSidebar"
          aria-label="Открыть или закрыть боковую панель"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <aside class="term-sidebar">
          <div class="term-sidebar-inner">
            <RouterLink 
              to="/robots" 
              class="term-sidebar-link" 
              :class="{ 'term-active': isActive('/robots') || isActive('/dashboard') }"
            >
              <span class="term-sidebar-icon">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="3" y="4" width="14" height="12" rx="1"/>
                  <path d="M3 8h14M7 4V2M13 4V2"/>
                </svg>
              </span>
              <span>Роботы</span>
            </RouterLink>
            <RouterLink 
              to="/orchestration" 
              class="term-sidebar-link" 
              data-testid="nav-orchestration"
              :class="{ 'term-active': isActive('/orchestration') }"
            >
              <span class="term-sidebar-icon">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="2" y="4" width="6" height="6" rx="1"/>
                  <rect x="12" y="4" width="6" height="6" rx="1"/>
                  <path d="M5 10h10M10 7v6"/>
                </svg>
              </span>
              <span>Ресурсы</span>
            </RouterLink>
            <RouterLink 
              to="/account" 
              class="term-sidebar-link"
              :class="{ 'term-active': isActive('/account') }"
            >
              <span class="term-sidebar-icon">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="10" cy="7" r="3"/>
                  <path d="M4 17c1.5-3 10.5-3 12 0"/>
                </svg>
              </span>
              <span>Аккаунт</span>
            </RouterLink>
            <RouterLink 
              to="/pairing" 
              class="term-sidebar-link"
              :class="{ 'term-active': isActive('/pairing') }"
            >
              <span class="term-sidebar-icon">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M10 2v4M10 14v4M2 10h4M14 10h4"/>
                  <circle cx="10" cy="10" r="3"/>
                </svg>
              </span>
              <span>Привязка</span>
            </RouterLink>
          </div>
        </aside>
      </div>
      
      <div class="term-app-main">
        <main class="term-main term-main-full">
          <div class="term-main-inner">
            <slot />
          </div>
        </main>
        <footer class="term-footer">
          <span v-if="user">{{ user.name }} ({{ isAdmin ? 'Admin' : 'User' }}) · </span>
          WolfpackCloud Control
        </footer>
      </div>
    </div>
  </div>
</template>
