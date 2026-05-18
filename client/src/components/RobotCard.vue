<script setup lang="ts">
import { computed } from 'vue'
import type { Robot, RobotStatus } from '@/types'

const props = defineProps<{
  robot: Robot
}>()

defineEmits<{
  click: []
}>()

function getStatusDotClass(status: RobotStatus): string {
  switch (status) {
    case 'active': return 'term-status-dot-active'
    case 'pending': return 'term-status-dot-pending'
    case 'error': return 'term-status-dot-error'
    default: return 'term-status-dot-inactive'
  }
}

function getStatusLabel(status: RobotStatus): string {
  switch (status) {
    case 'active': return 'Активен'
    case 'pending': return 'Ожидание'
    case 'error': return 'Ошибка'
    default: return 'Неактивен'
  }
}

const lastSeenFormatted = computed(() => {
  if (!props.robot.last_seen_at) return 'Никогда'
  const date = new Date(props.robot.last_seen_at)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  
  if (minutes < 1) return 'Только что'
  if (minutes < 60) return `${minutes} мин. назад`
  
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} ч. назад`
  
  const days = Math.floor(hours / 24)
  return `${days} дн. назад`
})
</script>

<template>
  <div
    class="term-card term-robot-card"
    @click="$emit('click')"
  >
    <div class="term-robot-card-header">
      <div style="flex: 1; min-width: 0;">
        <h3 class="term-robot-card-name">{{ robot.name }}</h3>
        <p class="term-robot-card-hostname">{{ robot.hostname }}</p>
      </div>
      <span class="term-status-cell">
        <span class="term-status-dot" :class="getStatusDotClass(robot.status)"></span>
        <span :class="'term-status-' + robot.status" class="term-fs-2xs">{{ getStatusLabel(robot.status) }}</span>
      </span>
    </div>

    <table class="term-robot-card-info">
      <tbody>
        <tr>
          <td>IP</td>
          <td>{{ robot.ip_address || '—' }}</td>
        </tr>
        <tr>
          <td>Arch</td>
          <td>{{ robot.architecture }}</td>
        </tr>
        <tr>
          <td>Last</td>
          <td>{{ lastSeenFormatted }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.term-robot-card {
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.term-robot-card:hover {
  border-color: var(--accent);
}

.term-robot-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.term-robot-card-name {
  font-size: var(--fs-sm);
  font-weight: 500;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.term-robot-card-hostname {
  font-size: var(--fs-2xs);
  color: var(--text-dim);
  margin: 0.125rem 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.term-robot-card-info {
  width: 100%;
  font-size: var(--fs-2xs);
  border-collapse: collapse;
}

.term-robot-card-info td {
  padding: 0.125rem 0;
  border: none;
}

.term-robot-card-info td:first-child {
  color: var(--text-dim);
  width: 3rem;
}

.term-robot-card-info td:last-child {
  text-align: left;
  color: var(--text);
}
</style>
