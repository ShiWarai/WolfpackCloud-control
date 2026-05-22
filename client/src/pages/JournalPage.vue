<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { logsApi, type LogsStatus, type RosLogEntry } from '@/api/logs'
import { eventsApi, type DeploymentEvent } from '@/api/events'

const activeTab = ref<'ros_logs' | 'deployment_events'>('ros_logs')
const logLimit = ref(200)
const eventLimit = ref(200)
const eventStatusFilter = ref('')

const logEntries = ref<RosLogEntry[]>([])
const logsStatus = ref<LogsStatus | null>(null)
const logsFetchError = ref<string | null>(null)
const deploymentEvents = ref<DeploymentEvent[]>([])
const logsInitialLoading = ref(false)
const eventsInitialLoading = ref(false)
const logContainerRef = ref<HTMLElement | null>(null)
const knownLogIds = new Set<number>()
const LOGS_MAX_LINES = 300
let pollTimer: ReturnType<typeof setInterval> | null = null

function formatLogLine(e: RosLogEntry): string {
  const net = e.network_id != null ? `[net:${e.network_id}] ` : ''
  return `[${e.recorded_at}] ${net}${e.level ?? ''} ${e.ros_node_name ?? ''}: ${e.message}`
}

function resetLogsState() {
  logEntries.value = []
  knownLogIds.clear()
}

function sortLogEntries(entries: RosLogEntry[]): RosLogEntry[] {
  return [...entries].sort((a, b) => {
    const ta = new Date(a.recorded_at).getTime()
    const tb = new Date(b.recorded_at).getTime()
    if (ta !== tb) return ta - tb
    return a.id - b.id
  })
}

function mergeLogEntries(incoming: RosLogEntry[]): boolean {
  const added: RosLogEntry[] = []
  for (const entry of sortLogEntries(incoming)) {
    if (knownLogIds.has(entry.id)) continue
    knownLogIds.add(entry.id)
    added.push(entry)
  }
  if (!added.length) return false

  logEntries.value = [...logEntries.value, ...added]
  if (logEntries.value.length > LOGS_MAX_LINES) {
    const dropped = logEntries.value.splice(0, logEntries.value.length - LOGS_MAX_LINES)
    for (const entry of dropped) knownLogIds.delete(entry.id)
  }
  return true
}

async function scrollLogsToBottomIfPinned() {
  await nextTick()
  const el = logContainerRef.value
  if (!el) return
  const pinThreshold = 48
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < pinThreshold
  if (atBottom || logsInitialLoading.value) {
    el.scrollTop = el.scrollHeight
  }
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

function isLogsUnavailable(): boolean {
  return !!logsAvailabilityMessage()
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
    const hadNew = mergeLogEntries(incoming)
    if (hadNew) await scrollLogsToBottomIfPinned()
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

function startPolling() {
  stopPolling()
  void refreshActiveTab(true)
  pollTimer = setInterval(() => {
    void refreshActiveTab(false)
  }, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(activeTab, () => {
  startPolling()
})

watch([logLimit, eventLimit, eventStatusFilter], () => {
  void refreshActiveTab(true)
})

onMounted(() => {
  startPolling()
})

onUnmounted(() => {
  stopPolling()
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
          <div class="term-card term-log-card">
            <div class="journal-toolbar">
              <h2 class="term-log-title">
                ROS-логи (/rosout)
                <span
                  class="journal-hint"
                  title="Все сообщения rosout-bridge из InfluxDB. Обновление каждые ~5 с."
                >?</span>
              </h2>
              <label class="journal-filter">
                <span class="term-text-dim">Строк:</span>
                <select v-model.number="logLimit" class="term-input journal-select">
                  <option :value="100">100</option>
                  <option :value="200">200</option>
                  <option :value="500">500</option>
                </select>
              </label>
            </div>
            <div
              v-if="isLogsUnavailable()"
              class="term-alert term-alert-error journal-status-alert"
            >
              {{ logsAvailabilityMessage() }}
            </div>
            <div ref="logContainerRef" class="term-log-viewport">
              <div
                v-if="logsInitialLoading && !logEntries.length"
                class="term-text-dim term-log-placeholder"
              >
                Загрузка...
              </div>
              <div
                v-else-if="!logEntries.length"
                class="term-text-dim term-log-placeholder"
              >
                Нет записей в журнале.
              </div>
              <div
                v-for="entry in logEntries"
                :key="entry.id"
                class="term-log-line"
              >
                {{ formatLogLine(entry) }}
              </div>
            </div>
          </div>
        </div>

        <div v-show="activeTab === 'deployment_events'" class="term-robot-panel term-active">
          <div class="term-card">
            <div class="journal-toolbar">
              <h2 class="term-log-title">
                События деплоя
                <span
                  class="journal-hint"
                  title="Запуск, миграция и остановка workloads из оркестрации. Обновление каждые ~5 с."
                >?</span>
              </h2>
              <div class="journal-filters-row">
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
              </div>
            </div>

            <div v-if="eventsInitialLoading && !deploymentEvents.length" class="term-text-dim">
              Загрузка...
            </div>
            <div v-else-if="!deploymentEvents.length" class="term-text-dim">
              Нет событий.
            </div>
            <div v-else class="journal-table-wrap">
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
                  <tr v-for="ev in deploymentEvents" :key="ev.id">
                    <td>{{ formatDate(ev.created_at) }}</td>
                    <td>{{ ev.deployment }}</td>
                    <td>{{ formatHostRoute(ev.from_host, ev.to_host) }}</td>
                    <td>{{ statusLabel(ev.status) }}</td>
                    <td>{{ ev.preset_id || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </DefaultLayout>
</template>

<style scoped>
.term-log-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.term-log-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
}

.journal-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.journal-filters-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

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

.journal-hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 0.95rem;
  height: 0.95rem;
  border: 1px solid var(--border);
  border-radius: 50%;
  font-size: 0.625rem;
  line-height: 1;
  color: var(--text-dim);
  cursor: help;
  flex-shrink: 0;
}

.journal-hint:hover {
  color: var(--accent, #fb923c);
  border-color: rgba(251, 146, 60, 0.55);
}

.term-log-viewport {
  height: min(32rem, calc(100vh - 12rem));
  min-height: 14rem;
  overflow: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 0.75rem 1rem;
  font-size: var(--fs-xs);
  line-height: 1.45;
  color: var(--text-dim);
}

.term-log-line {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.term-log-line + .term-log-line {
  margin-top: 0.15rem;
}

.term-log-placeholder {
  font-size: var(--fs-xs);
}

.journal-status-alert {
  margin-bottom: 0.75rem;
  font-size: var(--fs-xs);
}

.journal-table-wrap {
  overflow: auto;
}
</style>
