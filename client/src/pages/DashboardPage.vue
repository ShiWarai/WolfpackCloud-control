<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useAuthStore, useRobotsStore } from '@/stores'
import ExternalLinks from '@/components/ExternalLinks.vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const authStore = useAuthStore()
const robotsStore = useRobotsStore()

const user = computed(() => authStore.user)
const stats = computed(() => robotsStore.robotsByStatus)
const totalRobots = computed(() => robotsStore.total)

onMounted(() => {
  robotsStore.fetchRobots()
})
</script>

<template>
  <DefaultLayout>
    <div class="term-page-title-row">
      <h1 class="term-page-title">Dashboard</h1>
    </div>
    
    <p class="term-text-dim term-mb-1">
      Добро пожаловать, {{ user?.name }}!
    </p>

    <div class="term-dashboard-metrics">
      <div class="term-dashboard-metric">
        <span class="term-metric-label">Всего</span>
        <span class="term-metric-value">{{ totalRobots }}</span>
      </div>
      <div class="term-dashboard-metric">
        <span class="term-metric-label">Активных</span>
        <span class="term-metric-value term-status-active">{{ stats.active }}</span>
      </div>
      <div class="term-dashboard-metric">
        <span class="term-metric-label">Ожидают</span>
        <span class="term-metric-value term-status-pending">{{ stats.pending }}</span>
      </div>
      <div class="term-dashboard-metric">
        <span class="term-metric-label">Неактивных</span>
        <span class="term-metric-value term-status-inactive">{{ stats.inactive }}</span>
      </div>
      <div class="term-dashboard-metric">
        <span class="term-metric-label">С ошибками</span>
        <span class="term-metric-value term-status-error">{{ stats.error }}</span>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); gap: 1rem;">
      <ExternalLinks />

      <div class="term-card">
        <h2>Быстрые действия</h2>
        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
          <RouterLink to="/pairing" class="term-btn term-btn-primary">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" style="width: 1rem; height: 1rem;">
              <path d="M10 2v16M2 10h16"/>
            </svg>
            Привязать робота
          </RouterLink>
          <RouterLink to="/robots" class="term-btn">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" style="width: 1rem; height: 1rem;">
              <rect x="3" y="4" width="14" height="12" rx="1"/>
              <path d="M3 8h14"/>
            </svg>
            Все роботы
          </RouterLink>
        </div>
      </div>
    </div>
  </DefaultLayout>
</template>
