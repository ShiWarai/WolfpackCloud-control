<script setup lang="ts">
import { ref, watch } from 'vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import LogScrollPanel from '@/components/LogScrollPanel.vue'
import { logsApi, type LogsStatus, type RosLogEntry } from '@/api/logs'
import { eventsApi, type DeploymentEvent } from '@/api/events'
import { useRosLogBuffer } from '@/composables/useRosLogBuffer'
import { useIntervalPoll } from '@/composables/useIntervalPoll'

const activeTab = ref<'ros_logs' | 'deployment_events'>('ros_logs')
const logLimit = ref(200)
const eventLimit = ref(200)
const eventStatusFilter = ref('')

const logFreezeTrim = ref(false)
const {
  entries: logEntries,
  reset: resetLogsState,
  merge: mergeLogEntries,
  trimNow: trimLogBuffer,
  scrollGeneration: logScrollGeneration,
} = useRosLogBuffer(300, logFreezeTrim)

watch(logFreezeTrim, (frozen) => {
  if (!frozen) trimLogBuffer()
})
const logsStatus = ref<LogsStatus | null>(null)
const logsFetchError = ref<string | null>(null)
const deploymentEvents = ref<DeploymentEvent[]>([])
const logsInitialLoading = ref(false)
const eventsInitialLoading = ref(false)

function formatLogLine(e: RosLogEntry): string {
  const net = e.network_id != null ? `[net:${e.network_id}] ` : ''
  return `[${e.recorded_at}] ${net}${e.level ?? ''} ${e.ros_node_name ?? ''}: ${e.message}`
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('ru-RU')
}

function formatHostRoute(from: string | null, to: string | null): string {
  const f = from || '—'
  const t = to || '—'
  if (f === '—' && t === '—') return '—'
  return `${f} → ${t}`
}

function statusLabel(status: string): string {
  switch (status) {
    case 'started': return 'Запуск'
    case 'success': return 'Успех'
    case 'failed': return 'Ошибка'
    case 'stopped': return 'Остановлен'
    default: return status
  }
}

function logsAvailabilityMessage(): string | null {
  if (logsFetchError.value) return logsFetchError.value
  return logsStatus.value?.message ?? null
}

async function refreshLogsStatus() {
  try {
    logsStatus.value = await logsApi.getStatus()
  } catch {
    logsStatus.value = null
  }
}

async function refreshRosLogs(initial = false) {
  if (activeTab.value !== 'ros_logs') return
  if (initial) {
    resetLogsState()
    logsInitialLoading.value = true
    logsFetchError.value = null
    await refreshLogsStatus()
  }
  try {
    const incoming = await logsApi.list(undefined, logLimit.value)
    logsFetchError.value = null
    mergeLogEntries(incoming)
  } catch (err: unknown) {
    const status = (err as { response?: { status?: number; data?: { detail?: string } } })
      ?.response?.status
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    if (status === 503) {
      logsFetchError.value = 'InfluxDB не настроен — логи недоступны.'
    } else if (status === 502) {
      logsFetchError.value = detail
        ? `InfluxDB недоступен: ${detail}`
        : 'InfluxDB недоступен — логи временно недоступны.'
    } else {
      logsFetchError.value = 'Не удалось загрузить логи.'
    }
    if (initial) resetLogsState()
  } finally {
    if (initial) logsInitialLoading.value = false
  }
}

async function refreshDeploymentEvents(initial = false) {
  if (activeTab.value !== 'deployment_events') return
  if (initial) eventsInitialLoading.value = true
  try {
    const status = eventStatusFilter.value.trim() || undefined
    deploymentEvents.value = await eventsApi.listDeployments(
      eventLimit.value,
      status,
    )
  } catch {
    if (initial) deploymentEvents.value = []
  } finally {
    if (initial) eventsInitialLoading.value = false
  }
}

async function refreshActiveTab(initial = false) {
  if (activeTab.value === 'ros_logs') {
    await refreshRosLogs(initial)
  } else {
    await refreshDeploymentEvents(initial)
  }
}

const journalPoll = useIntervalPoll({
  intervalMs: 5000,
  enabled: () => true,
  fetch: (initial) => refreshActiveTab(initial),
  pauseWhenHidden: true,
})

watch(activeTab, (tab, prev) => {
  if (tab === prev) return
  void journalPoll.triggerNow(true)
})

watch([logLimit, eventLimit, eventStatusFilter], () => {
  void journalPoll.triggerNow(true)
})
</script>

<template>
  <DefaultLayout>
    <div class="term-page-title-row">
      <h1 class="term-page-title">Журнал</h1>
    </div>

    <div class="term-robot-layout">
      <nav class="term-robot-sidebar">
        <a
          href="#"
          @click.prevent="activeTab = 'ros_logs'"
          :class="{ 'term-active': activeTab === 'ros_logs' }"
        >
          <span class="term-tab-icon">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M3 5h14M3 10h10M3 15h7"/>
            </svg>
          </span>
          ROS-логи
        </a>
        <a
          href="#"
          @click.prevent="activeTab = 'deployment_events'"
          :class="{ 'term-active': activeTab === 'deployment_events' }"
        >
          <span class="term-tab-icon">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="4" width="14" height="12" rx="1"/>
              <path d="M7 8h6M7 12h4"/>
            </svg>
          </span>
          События деплоя
        </a>
      </nav>

      <div class="term-robot-content">
        <div v-show="activeTab === 'ros_logs'" class="term-robot-panel term-active">
          <LogScrollPanel
            v-model:freeze-trim="logFreezeTrim"
            title="ROS-логи (/rosout)"
            hint="Все сообщения rosout-bridge из InfluxDB. Обновление каждые ~5 с."
            :loading="logsInitialLoading"
            :empty="!logEntries.length"
            empty-text="Нет записей в журнале."
            :alert-text="logsAvailabilityMessage()"
            :scroll-trigger="logScrollGeneration"
          >
            <template #toolbar>
              <label class="journal-filter">
                <span class="term-text-dim">Строк:</span>
                <select v-model.number="logLimit" class="term-input journal-select">
                  <option :value="100">100</option>
                  <option :value="200">200</option>
                  <option :value="500">500</option>
                </select>
              </label>
            </template>
            <div
              v-for="entry in logEntries"
              :key="entry.id"
              :data-log-entry-id="entry.id"
              class="log-scroll-panel__line"
            >
              {{ formatLogLine(entry) }}
            </div>
          </LogScrollPanel>
        </div>

        <div v-show="activeTab === 'deployment_events'" class="term-robot-panel term-active">
          <LogScrollPanel
            title="События деплоя"
            hint="Запуск, миграция и остановка workloads из оркестрации. Обновление каждые ~5 с."
            variant="plain"
            scroll-mode="top"
            :loading="eventsInitialLoading"
            :empty="!deploymentEvents.length"
            empty-text="Нет событий."
            :scroll-trigger="deploymentEvents.length"
          >
            <template #toolbar>
              <label class="journal-filter">
                <span class="term-text-dim">Статус:</span>
                <select v-model="eventStatusFilter" class="term-input journal-select">
                  <option value="">Все</option>
                  <option value="started">Запуск</option>
                  <option value="success">Успех</option>
                  <option value="failed">Ошибка</option>
                  <option value="stopped">Остановлен</option>
                </select>
              </label>
              <label class="journal-filter">
                <span class="term-text-dim">Строк:</span>
                <select v-model.number="eventLimit" class="term-input journal-select">
                  <option :value="100">100</option>
                  <option :value="200">200</option>
                  <option :value="500">500</option>
                </select>
              </label>
            </template>
            <table class="term-table">
              <thead>
                <tr>
                  <th>Время</th>
                  <th>Deployment</th>
                  <th>Маршрут</th>
                  <th>Статус</th>
                  <th>Пресет</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="ev in deploymentEvents" :key="ev.id" :data-log-entry-id="ev.id">
                  <td>{{ formatDate(ev.created_at) }}</td>
                  <td>{{ ev.deployment }}</td>
                  <td>{{ formatHostRoute(ev.from_host, ev.to_host) }}</td>
                  <td>{{ statusLabel(ev.status) }}</td>
                  <td>{{ ev.preset_id || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </LogScrollPanel>
        </div>
      </div>
    </div>
  </DefaultLayout>
</template>

<style scoped>
.journal-filter {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--fs-xs);
}

.journal-select {
  width: auto;
  min-width: 5.5rem;
  padding: 0.25rem 0.5rem;
  font-size: var(--fs-xs);
}
</style>
