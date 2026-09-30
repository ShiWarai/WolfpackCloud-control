<script setup lang="ts">
import { computed } from 'vue'

import type { AsyncTask } from '@/composables/useAsyncTaskQueue'
import type { MigrationWatch, OrchestrationTaskMeta } from '@/composables/useOrchestrationTasks'

const props = defineProps<{
  tasks: AsyncTask<OrchestrationTaskMeta>[]
  migrationWatches: MigrationWatch[]
  isMigrateRunning: (deployment: string) => boolean
}>()

interface DisplayItem {
  id: string
  label: string
  detail?: string
  tone: 'queued' | 'running' | 'watching' | 'failed'
}

const items = computed<DisplayItem[]>(() => {
  const out: DisplayItem[] = []

  for (const task of props.tasks) {
    if (task.status !== 'queued' && task.status !== 'running' && task.status !== 'failed') continue
    const dep = task.meta.deployment
    if (task.meta.kind === 'migrate') {
      const target = task.meta.targetNode ?? '—'
      if (task.status === 'queued') {
        out.push({
          id: task.id,
          label: `Ожидает: перенос «${dep}» → ${target}`,
          tone: 'queued',
        })
      } else if (task.status === 'running') {
        out.push({
          id: task.id,
          label: `Выполняется: перенос «${dep}» → ${target}`,
          detail: 'Отправка запроса…',
          tone: 'running',
        })
      } else {
        out.push({
          id: task.id,
          label: `Ошибка переноса «${dep}»`,
          detail: task.error,
          tone: 'failed',
        })
      }
      continue
    }

    if (task.status === 'queued') {
      out.push({ id: task.id, label: `Ожидает: остановка «${dep}»`, tone: 'queued' })
    } else if (task.status === 'running') {
      out.push({
        id: task.id,
        label: `Выполняется: остановка «${dep}»`,
        tone: 'running',
      })
    } else {
      out.push({
        id: task.id,
        label: `Ошибка остановки «${dep}»`,
        detail: task.error,
        tone: 'failed',
      })
    }
  }

  for (const watch of props.migrationWatches) {
    if (props.isMigrateRunning(watch.deployment)) continue
    out.push({
      id: `watch-${watch.deployment}`,
      label: `Перенос «${watch.deployment}» → ${watch.targetNode}`,
      detail: 'Ожидание готовности деплоймента на целевой ноде.',
      tone: 'watching',
    })
  }

  return out
})

const visible = computed(() => items.value.length > 0)
</script>

<template>
  <div v-if="visible" class="orchestration-task-queue term-mb-1">
    <div
      v-for="item in items"
      :key="item.id"
      class="orchestration-task-queue__item"
      :class="`orchestration-task-queue__item--${item.tone}`"
    >
      <div>{{ item.label }}</div>
      <p v-if="item.detail" class="term-text-dim term-fs-2xs term-mt-1" style="margin: 0;">
        {{ item.detail }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.orchestration-task-queue {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.orchestration-task-queue__item {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  font-size: var(--fs-xs);
}

.orchestration-task-queue__item--queued {
  border-color: rgba(148, 163, 184, 0.45);
  background: rgba(148, 163, 184, 0.08);
}

.orchestration-task-queue__item--running,
.orchestration-task-queue__item--watching {
  border-color: rgba(251, 146, 60, 0.55);
  background: rgba(251, 146, 60, 0.08);
  color: var(--accent, #fb923c);
}

.orchestration-task-queue__item--failed {
  border-color: rgba(248, 113, 113, 0.55);
  background: rgba(248, 113, 113, 0.08);
  color: #f87171;
}
</style>
