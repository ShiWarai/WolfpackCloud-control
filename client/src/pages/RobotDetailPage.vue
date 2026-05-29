<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRobotsStore } from '@/stores'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import ExternalLinks from '@/components/ExternalLinks.vue'
import LogScrollPanel from '@/components/LogScrollPanel.vue'
import { logsApi } from '@/api/logs'
import type { RosLogEntry } from '@/api/logs'
import { networksApi, type Network } from '@/api/networks'
import type { RobotStatus } from '@/types'
import { useRosLogBuffer } from '@/composables/useRosLogBuffer'
import { useIntervalPoll } from '@/composables/useIntervalPoll'

const route = useRoute()
const router = useRouter()
const robotsStore = useRobotsStore()

const activeTab = ref<'info' | 'metrics' | 'logs'>('info')
const editing = ref(false)
const editName = ref('')
const editDescription = ref('')
const editNetworkIdStr = ref('')
const networks = ref<Network[]>([])
const showDeleteConfirm = ref(false)

const { entries: logEntries, reset: resetLogsState, merge: mergeLogEntries } =
  useRosLogBuffer(150)
const logsInitialLoading = ref(false)
const logsRefreshInFlight = ref<Promise<void> | null>(null)
/** Инвалидируется при unmount / смене робота — игнорируем устаревшие fetch. */
let logsFetchSession = 0

function invalidateLogsFetch() {
  logsFetchSession += 1
  logsRefreshInFlight.value = null
}

function formatLogLine(e: RosLogEntry): string {
  return `[${e.recorded_at}] ${e.level ?? ''} ${e.ros_node_name ?? ''}: ${e.message}`
}

const LOGS_MAX_LINES = 150

const robot = computed(() => robotsStore.currentRobot)
const robotId = computed(() => Number(route.params.id))

const robotNetworkLabel = computed(() => {
  const r = robot.value
  if (!r?.network_id) return '—'
  const n = networks.value.find((x) => x.id === r.network_id)
  return n ? `${n.name} (DOMAIN ${n.ros_domain_id})` : `Сеть #${r.network_id}`
})

async function loadNetworks() {
  try {
    networks.value = await networksApi.list()
  } catch {
    networks.value = []
  }
}

async function refreshLogs(initial = false) {
  if (!robot.value || activeTab.value !== 'logs') return

  const session = logsFetchSession
  const inFlight = logsRefreshInFlight.value
  if (inFlight) {
    if (!initial) return
    await inFlight
    if (session !== logsFetchSession) return
  }

  const run = async () => {
    if (session !== logsFetchSession) return
    if (initial) {
      resetLogsState()
      logsInitialLoading.value = true
    }
    try {
      if (session !== logsFetchSession) return
      const nid = robot.value!.network_id ?? undefined
      const incoming = await logsApi.list(nid, LOGS_MAX_LINES)
      if (session !== logsFetchSession) return
      mergeLogEntries(incoming)
    } catch {
      if (session !== logsFetchSession) return
      if (initial) resetLogsState()
    } finally {
      if (session === logsFetchSession && initial) {
        logsInitialLoading.value = false
      }
    }
  }

  const promise = run()
  logsRefreshInFlight.value = promise
  try {
    await promise
  } finally {
    if (logsRefreshInFlight.value === promise) {
      logsRefreshInFlight.value = null
    }
  }
}

const logsPoll = useIntervalPoll({
  intervalMs: 4000,
  enabled: () => activeTab.value === 'logs',
  enabledDebounceMs: 150,
  fetch: (initial) => refreshLogs(initial),
  pauseWhenHidden: true,
})

watch(robotId, () => {
  invalidateLogsFetch()
  resetLogsState()
  if (activeTab.value === 'logs') void logsPoll.triggerNow(true)
})

watch(
  () => robot.value?.network_id,
  () => {
    invalidateLogsFetch()
    resetLogsState()
    if (activeTab.value === 'logs') void logsPoll.triggerNow(true)
  }
)

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

function startEditing() {
  if (robot.value) {
    editName.value = robot.value.name
    editDescription.value = robot.value.description || ''
    editNetworkIdStr.value =
      robot.value.network_id != null ? String(robot.value.network_id) : ''
    editing.value = true
  }
}

async function saveChanges() {
  try {
    await robotsStore.updateRobot(robotId.value, {
      name: editName.value,
      description: editDescription.value || undefined,
      network_id:
        editNetworkIdStr.value === '' ? null : Number(editNetworkIdStr.value),
    })
    editing.value = false
    void refreshLogs(true)
  } catch {
    // error handled in store
  }
}

function cancelEditing() {
  editing.value = false
}

async function deleteRobot() {
  try {
    await robotsStore.deleteRobot(robotId.value)
    router.push('/robots')
  } catch {
    // error handled in store
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('ru-RU')
}

onMounted(() => {
  void Promise.all([
    robotsStore.fetchRobot(robotId.value),
    loadNetworks(),
  ])
})

onUnmounted(() => {
  invalidateLogsFetch()
})
</script>

<template>
  <DefaultLayout>
    <div class="term-page-title-row">
      <div style="display: flex; align-items: center; gap: 0.75rem;">
        <button @click="router.back()" class="term-btn term-btn-icon" title="Назад">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M15 19l-7-7 7-7"/>
          </svg>
        </button>
        <h1 class="term-page-title">{{ robot?.name || 'Загрузка...' }}</h1>
        <span v-if="robot" class="term-status-cell" style="margin-left: 0.5rem;">
          <span class="term-status-dot" :class="getStatusDotClass(robot.status)"></span>
          <span class="term-text-dim term-fs-2xs">{{ getStatusLabel(robot.status) }}</span>
        </span>
      </div>
      <div v-if="robot && !editing" style="display: flex; gap: 0.5rem;">
        <button @click="startEditing" class="term-btn">Редактировать</button>
        <button @click="showDeleteConfirm = true" class="term-btn term-btn-delete">Удалить</button>
      </div>
    </div>

    <div v-if="robotsStore.loading" class="term-card" style="text-align: center; padding: 2rem;">
      <p class="term-text-dim">Загрузка...</p>
    </div>

    <div v-else-if="robotsStore.error" class="term-alert term-alert-error">
      {{ robotsStore.error }}
    </div>

    <template v-else-if="robot">
      <div class="term-robot-layout">
        <nav class="term-robot-sidebar">
          <a
            href="#"
            @click.prevent="activeTab = 'info'"
            :class="{ 'term-active': activeTab === 'info' }"
          >
            <span class="term-tab-icon">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="10" cy="10" r="7"/>
                <path d="M10 7v0m0 3v4"/>
              </svg>
            </span>
            Информация
          </a>
          <a
            href="#"
            @click.prevent="activeTab = 'metrics'"
            :class="{ 'term-active': activeTab === 'metrics' }"
          >
            <span class="term-tab-icon">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M3 17V8l4 3v6M9 17V5l4 5v7M15 17v-6l3 2v4"/>
              </svg>
            </span>
            Метрики
          </a>
          <a
            href="#"
            @click.prevent="activeTab = 'logs'"
            :class="{ 'term-active': activeTab === 'logs' }"
          >
            <span class="term-tab-icon">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M3 5h14M3 10h10M3 15h7"/>
              </svg>
            </span>
            Логи
          </a>
        </nav>
        
        <div class="term-robot-content">
          <div v-show="activeTab === 'info'" class="term-robot-panel term-active">
            <form v-if="editing" @submit.prevent="saveChanges" class="term-form">
              <div class="term-field">
                <label for="editName">Имя</label>
                <input id="editName" v-model="editName" type="text" required class="term-input" style="max-width: none;"/>
              </div>
              <div class="term-field">
                <label for="editDescription">Описание</label>
                <textarea id="editDescription" v-model="editDescription" rows="3" class="term-input" style="max-width: none; resize: vertical;"></textarea>
              </div>
              <div class="term-field">
                <label for="editNetwork">Сеть (ROS_DOMAIN_ID)</label>
                <select
                  id="editNetwork"
                  v-model="editNetworkIdStr"
                  class="term-input"
                  style="max-width: none;"
                >
                  <option value="">Не привязан</option>
                  <option
                    v-for="n in networks"
                    :key="n.id"
                    :value="String(n.id)"
                  >
                    {{ n.name }} — DOMAIN {{ n.ros_domain_id }}
                  </option>
                </select>
              </div>
              <div style="display: flex; gap: 0.5rem;">
                <button type="button" @click="cancelEditing" class="term-btn">Отмена</button>
                <button type="submit" class="term-btn term-btn-primary">Сохранить</button>
              </div>
            </form>

            <div v-else>
              <table class="term-table" style="margin-bottom: 1rem;">
                <tbody>
                  <tr>
                    <td style="color: var(--text-dim); width: 35%;">Имя</td>
                    <td>{{ robot.name }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">Hostname</td>
                    <td>{{ robot.hostname }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">Сеть (ROS_DOMAIN_ID)</td>
                    <td>{{ robotNetworkLabel }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">IP-адрес</td>
                    <td>{{ robot.ip_address || '—' }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">Архитектура</td>
                    <td>{{ robot.architecture }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">Описание</td>
                    <td>{{ robot.description || '—' }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">Создан</td>
                    <td>{{ formatDate(robot.created_at) }}</td>
                  </tr>
                  <tr>
                    <td style="color: var(--text-dim);">Последняя активность</td>
                    <td>{{ formatDate(robot.last_seen_at) }}</td>
                  </tr>
                </tbody>
              </table>

              <details v-if="robot.influxdb_token" class="term-token-spoiler term-card">
                <summary class="term-token-spoiler-summary">Токен InfluxDB</summary>
                <div class="term-token-spoiler-body">
                  <pre class="term-log term-token-value">{{ robot.influxdb_token }}</pre>
                  <p class="term-text-dim term-mt-1 term-fs-2xs">
                    Этот токен используется роботом для отправки метрик
                  </p>
                </div>
              </details>
            </div>
          </div>
          
          <div v-show="activeTab === 'metrics'" class="term-robot-panel term-active">
            <ExternalLinks :robot-id="robotId" />
            
            <div class="term-widget term-mt-1">
              <h2>Графики метрик</h2>
              <div class="term-widget-fill">
                Графики будут загружены из Grafana
              </div>
            </div>
          </div>
          
          <div v-show="activeTab === 'logs'" class="term-robot-panel term-active">
            <LogScrollPanel
              title="Логи ROS (/rosout)"
              hint="Из rosout-bridge для выбранной сети (привязка робота к ROS_DOMAIN_ID). Обновление каждые ~4 с."
              :loading="logsInitialLoading"
              :empty="!logEntries.length"
              empty-text="Нет записей (или rosout-bridge не запущен / нет network_id у робота)."
              :scroll-trigger="logEntries.length"
            >
              <div
                v-for="entry in logEntries"
                :key="entry.id"
                class="log-scroll-panel__line"
              >
                {{ formatLogLine(entry) }}
              </div>
            </LogScrollPanel>
          </div>
        </div>
      </div>
    </template>

    <div
      v-if="showDeleteConfirm"
      class="term-modal-overlay"
      @click.self="showDeleteConfirm = false"
    >
      <div class="term-modal">
        <h3 style="font-size: 1rem; margin: 0 0 0.5rem;">Удалить робота?</h3>
        <p class="term-text-dim term-mb-1">
          Это действие нельзя отменить. Все данные робота будут удалены.
        </p>
        <div style="display: flex; gap: 0.5rem;">
          <button @click="showDeleteConfirm = false" class="term-btn" style="flex: 1;">
            Отмена
          </button>
          <button @click="deleteRobot" class="term-btn term-btn-delete" style="flex: 1;">
            Удалить
          </button>
        </div>
      </div>
    </div>
  </DefaultLayout>
</template>

<style scoped>
.term-token-spoiler {
  margin-top: 1rem;
}

.term-token-spoiler-summary {
  cursor: pointer;
  font-size: var(--fs-sm, 0.875rem);
  font-weight: 500;
  color: var(--text);
  list-style: none;
  user-select: none;
}

.term-token-spoiler-summary::-webkit-details-marker {
  display: none;
}

.term-token-spoiler-summary::before {
  content: '▸ ';
  color: var(--accent, #fb923c);
}

.term-token-spoiler[open] .term-token-spoiler-summary::before {
  content: '▾ ';
}

.term-token-spoiler-summary:hover {
  color: var(--accent, #fb923c);
}

.term-token-spoiler-body {
  margin-top: 0.75rem;
}

.term-token-value {
  min-height: auto;
  margin: 0;
}

.term-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.term-modal {
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 1.5rem;
  max-width: 24rem;
  width: calc(100% - 2rem);
}
</style>
