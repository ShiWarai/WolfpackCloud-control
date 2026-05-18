<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRobotsStore, useAuthStore } from '@/stores'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import type { RobotStatus } from '@/types'

const robotsStore = useRobotsStore()
const authStore = useAuthStore()

const search = ref('')
const statusFilter = ref<RobotStatus | ''>('')
const searchTimeout = ref<number>()

const statusOptions: { value: RobotStatus | ''; label: string }[] = [
  { value: '', label: 'Все статусы' },
  { value: 'active', label: 'Активные' },
  { value: 'pending', label: 'Ожидающие' },
  { value: 'inactive', label: 'Неактивные' },
  { value: 'error', label: 'С ошибками' },
]

function fetchRobots() {
  robotsStore.fetchRobots({
    search: search.value || undefined,
    status: statusFilter.value || undefined,
  })
}

watch(search, () => {
  clearTimeout(searchTimeout.value)
  searchTimeout.value = window.setTimeout(fetchRobots, 300)
})

watch(statusFilter, fetchRobots)

function getStatusClass(status: string) {
  switch (status) {
    case 'active': return 'term-status-dot-active'
    case 'pending': return 'term-status-dot-pending'
    case 'error': return 'term-status-dot-error'
    default: return 'term-status-dot-inactive'
  }
}

function getStatusText(status: string) {
  switch (status) {
    case 'active': return 'Активен'
    case 'pending': return 'Ожидает'
    case 'error': return 'Ошибка'
    default: return 'Неактивен'
  }
}

function formatDate(dateStr: string | null | undefined) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

onMounted(fetchRobots)
</script>

<template>
  <DefaultLayout>
    <div class="term-page-title-row">
      <h1 class="term-page-title">Роботы</h1>
      <RouterLink to="/pairing" class="term-btn term-btn-primary">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" style="width: 1rem; height: 1rem;">
          <path d="M10 2v16M2 10h16"/>
        </svg>
        Привязать
      </RouterLink>
    </div>

    <div class="term-table-controls">
      <div class="term-table-search">
        <input
          v-model="search"
          type="text"
          placeholder="Поиск по имени или hostname..."
          class="term-input"
        />
        <select v-model="statusFilter" class="term-select" style="max-width: 10rem;">
          <option v-for="option in statusOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
    </div>

    <div v-if="robotsStore.loading" class="term-card" style="text-align: center; padding: 2rem;">
      <p class="term-text-dim">Загрузка...</p>
    </div>

    <div v-else-if="robotsStore.error" class="term-alert term-alert-error">
      {{ robotsStore.error }}
    </div>

    <div v-else-if="robotsStore.robots.length === 0" class="term-card" style="text-align: center; padding: 2rem;">
      <p class="term-text-dim term-mb-1">Роботы не найдены</p>
      <RouterLink to="/pairing" class="term-btn term-btn-primary">
        Привязать первого робота
      </RouterLink>
    </div>

    <table v-else class="term-table">
      <thead>
        <tr>
          <th>Имя / Hostname</th>
          <th>Статус</th>
          <th v-if="authStore.isAdmin">Владелец</th>
          <th>Последний отклик</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="robot in robotsStore.robots" :key="robot.id">
          <td>
            <RouterLink :to="`/robots/${robot.id}`">
              {{ robot.name || robot.hostname }}
            </RouterLink>
            <div class="term-text-dim term-fs-2xs" v-if="robot.name">
              {{ robot.hostname }}
            </div>
          </td>
          <td>
            <span class="term-status-cell">
              <span class="term-status-dot" :class="getStatusClass(robot.status)"></span>
              <span :class="'term-status-' + robot.status">{{ getStatusText(robot.status) }}</span>
            </span>
          </td>
          <td v-if="authStore.isAdmin">
            {{ robot.owner_id || '-' }}
          </td>
          <td class="term-text-dim">
            {{ formatDate(robot.last_seen_at) }}
          </td>
          <td>
            <div class="term-table-actions-cell">
              <RouterLink :to="`/robots/${robot.id}`" class="term-action-icon" title="Подробнее">
                →
              </RouterLink>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    
    <p class="term-text-dim term-mt-1">Всего: {{ robotsStore.total }}</p>
  </DefaultLayout>
</template>
