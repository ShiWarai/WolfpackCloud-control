<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { clusterApi } from '@/api/cluster'
import type {
  ClusterPod,
  ComputePreset,
  OrchestrationResponse,
  WorkerNode,
} from '@/api/cluster'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { workloadsApi } from '@/api/workloads'
import { useAuthStore } from '@/stores'

const authStore = useAuthStore()

/** Только первый запрос: полноэкранное «Загрузка…». Дальше данные не скрываем. */
const initialLoading = ref(true)
const hasLoadedOnce = ref(false)
/** Кнопка «Обновить» и лёгкая подсветка блока. */
const refreshing = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)
let successClearTimer: ReturnType<typeof setTimeout> | null = null

/** Только пока уходит PATCH миграции — блокируем DnD. Ожидание rolling на ноде не блокируем. */
const migrateInFlight = ref(false)
/** Показываем баннер и подсветку ноды, пока деплоймент не стабилизировался на целевой ноде. */
const migratePending = ref<{
  deployment: string
  targetNode: string
  startedAt: number
} | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollRequestInFlight = false

const MIGRATE_WATCH_MAX_MS = 15 * 60 * 1000
const NODE_HOSTNAME_SELECTOR = 'kubernetes.io/hostname'

const POLL_MS = 5000

const workerNodes = ref<WorkerNode[]>([])
const podsByNode = ref<Record<string, ClusterPod[]>>({})
const orphanPods = ref<ClusterPod[]>([])
const deployments = ref<OrchestrationResponse['deployments']>([])
const dragged = ref<{ deploymentName: string; podName: string } | null>(null)

const showLaunchModal = ref(false)
const launchInFlight = ref(false)
const autoOrchestrate = ref(false)
const computePresets = ref<ComputePreset[]>([])
const selectedPresetId = ref('')
const selectedNodeHostname = ref('')
const stopDeploymentInFlight = ref<string | null>(null)

/** Worker и dev в одном списке; порядок: worker → dev → прочие по имени. */
const ROLE_SORT_ORDER: Record<string, number> = { worker: 0, dev: 1 }

const sortedPoolNodes = computed(() =>
  [...workerNodes.value].sort((a, b) => {
    const rank = (n: WorkerNode) => {
      const r = (n.labels['wolfpack.io/role'] || '').toLowerCase()
      return r in ROLE_SORT_ORDER ? ROLE_SORT_ORDER[r] : 50
    }
    const d = rank(a) - rank(b)
    return d !== 0 ? d : a.name.localeCompare(b.name)
  }),
)

const showSkeleton = computed(() => initialLoading.value && !hasLoadedOnce.value)
const interactionLocked = computed(
  () =>
    migrateInFlight.value ||
    refreshing.value ||
    launchInFlight.value ||
    stopDeploymentInFlight.value !== null,
)

const migrateBannerVisible = computed(
  () => migratePending.value !== null || migrateInFlight.value,
)

function flashSuccess(text: string) {
  successMessage.value = text
  if (successClearTimer) clearTimeout(successClearTimer)
  successClearTimer = setTimeout(() => {
    successMessage.value = null
    successClearTimer = null
  }, 4500)
}

function tryFinishMigrationWatch() {
  const pending = migratePending.value
  if (!pending) return
  if (Date.now() - pending.startedAt > MIGRATE_WATCH_MAX_MS) {
    migratePending.value = null
    return
  }
  const dep = deployments.value.find((d) => d.name === pending.deployment)
  if (dep) {
    const sel = dep.nodeSelector || {}
    const onTarget = sel[NODE_HOSTNAME_SELECTOR] === pending.targetNode
    const want = dep.replicas ?? 0
    const ready = dep.readyReplicas ?? 0
    if (onTarget && want > 0 && ready >= want) {
      migratePending.value = null
      return
    }
  }
  const pods = podsMatchingDeployment(pending.deployment)
  if (
    pods.length > 0 &&
    pods.every(
      (p) =>
        p.nodeName === pending.targetNode &&
        (p.phase === 'Running' || p.phase === 'Succeeded'),
    )
  ) {
    migratePending.value = null
  }
}

function podsMatchingDeployment(deploymentName: string): ClusterPod[] {
  const out: ClusterPod[] = []
  for (const list of Object.values(podsByNode.value)) {
    for (const p of list) {
      if (p.deploymentName === deploymentName) out.push(p)
    }
  }
  for (const p of orphanPods.value) {
    if (p.deploymentName === deploymentName) out.push(p)
  }
  return out
}

async function load(opts?: { quiet?: boolean }) {
  const quiet = opts?.quiet === true
  if (!quiet) error.value = null
  if (!quiet) {
    if (!hasLoadedOnce.value) initialLoading.value = true
    else refreshing.value = true
  }
  try {
    const data = await clusterApi.getOrchestration()
    workerNodes.value = data.workerNodes
    podsByNode.value = data.podsByNode
    orphanPods.value = data.orphanPods ?? []
    deployments.value = data.deployments ?? []
    hasLoadedOnce.value = true
    tryFinishMigrationWatch()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    if (!quiet) {
      error.value = err.response?.data?.detail || 'Не удалось загрузить кластер'
    }
  } finally {
    initialLoading.value = false
    refreshing.value = false
  }
}

async function pollOrchestrationQuiet() {
  if (pollRequestInFlight) return
  pollRequestInFlight = true
  try {
    await load({ quiet: true })
  } finally {
    pollRequestInFlight = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    void pollOrchestrationQuiet()
  }, POLL_MS)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onDragStart(dep: string | undefined, pod: string, ev: DragEvent) {
  if (!dep || interactionLocked.value) return
  dragged.value = { deploymentName: dep, podName: pod }
  ev.dataTransfer?.setData('text/plain', dep)
}

function onDragEnd() {
  dragged.value = null
}

async function onDropNode(nodeName: string, ev: DragEvent) {
  ev.preventDefault()
  if (interactionLocked.value) return
  const dep = dragged.value?.deploymentName || ev.dataTransfer?.getData('text/plain')
  if (!dep) return
  migrateInFlight.value = true
  migratePending.value = {
    deployment: dep,
    targetNode: nodeName,
    startedAt: Date.now(),
  }
  error.value = null
  try {
    if (authStore.isAdmin) {
      await workloadsApi.migrateByDeploymentName(dep, nodeName)
    } else {
      try {
        await workloadsApi.migrateOwnedWorkload(dep, nodeName)
      } catch (e1: unknown) {
        const er1 = e1 as { response?: { status?: number } }
        if (er1.response?.status === 404) {
          await workloadsApi.migrateByDeploymentName(dep, nodeName)
        } else {
          throw e1
        }
      }
    }
    await load({ quiet: true })
    flashSuccess(`Перенос запущен: «${dep}» → ${nodeName}`)
  } catch (e: unknown) {
    migratePending.value = null
    const err = e as { response?: { data?: { detail?: string }; status?: number } }
    const detail = err.response?.data?.detail
    if (err.response?.status === 403) {
      error.value = detail || 'Недостаточно прав (нужна роль admin в Keycloak для чужих деплоев).'
    } else if (err.response?.status === 404) {
      error.value =
        detail ||
        'Этот Deployment не из каталога Control — назначьте роль admin в Keycloak или создайте workload через API/UI.'
    } else {
      error.value = detail || 'Ошибка миграции'
    }
  } finally {
    migrateInFlight.value = false
  }
}

async function openLaunchModal() {
  showLaunchModal.value = true
  error.value = null
  try {
    computePresets.value = await clusterApi.getComputePresets()
    if (!selectedPresetId.value && computePresets.value.length) {
      selectedPresetId.value = computePresets.value[0].id
    }
    if (!selectedNodeHostname.value && sortedPoolNodes.value.length) {
      const firstReady = sortedPoolNodes.value.find((n) => n.ready)
      selectedNodeHostname.value = (firstReady || sortedPoolNodes.value[0])?.name ?? ''
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Не удалось загрузить пресеты'
  }
}

function closeLaunchModal() {
  if (launchInFlight.value) return
  showLaunchModal.value = false
}

async function confirmLaunch() {
  if (!selectedPresetId.value) {
    error.value = 'Выберите тип пода'
    return
  }
  if (!autoOrchestrate.value && !selectedNodeHostname.value) {
    error.value = 'Выберите ноду или включите автоматическую оркестрацию'
    return
  }
  launchInFlight.value = true
  error.value = null
  try {
    const r = await clusterApi.launchComputePreset(selectedPresetId.value, {
      node_hostname: autoOrchestrate.value ? null : selectedNodeHostname.value,
      auto_orchestrate: autoOrchestrate.value,
    })
    flashSuccess(`Запущено: «${r.deployment_name}» на ${r.node_hostname} (${r.architecture})`)
    showLaunchModal.value = false
    await load({ quiet: true })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    error.value = err.response?.data?.detail || 'Не удалось запустить пресет'
  } finally {
    launchInFlight.value = false
  }
}

async function onStopDeployment(deploymentName: string | undefined) {
  if (!deploymentName || interactionLocked.value) return
  stopDeploymentInFlight.value = deploymentName
  error.value = null
  try {
    await clusterApi.stopDeployment(deploymentName)
    flashSuccess(`Остановлен деплоймент «${deploymentName}»`)
    await load({ quiet: true })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string }; status?: number } }
    error.value = err.response?.data?.detail || 'Не удалось остановить деплоймент'
  } finally {
    stopDeploymentInFlight.value = null
  }
}

onMounted(async () => {
  await authStore.fetchUser()
  await load()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  if (successClearTimer) clearTimeout(successClearTimer)
})
</script>

<template>
  <DefaultLayout>
    <div class="term-page-title-row">
      <h1 class="term-page-title">Ресурсы кластера</h1>
      <div class="orchestration-title-actions">
        <button
          type="button"
          class="term-btn"
          :disabled="interactionLocked"
          @click="openLaunchModal()"
        >
          Запустить
        </button>
        <button
          type="button"
          class="term-btn"
          :disabled="interactionLocked"
          @click="load()"
        >
          {{ refreshing ? 'Обновление…' : 'Обновить' }}
        </button>
      </div>
    </div>

    <p class="term-text-dim term-mb-1">Перетащите карточку пода на ноду пула.</p>

    <div v-if="error" class="term-alert term-alert-error term-mb-1">{{ error }}</div>
    <div v-if="successMessage" class="term-alert term-alert-success term-mb-1">{{ successMessage }}</div>

    <div
      v-if="migrateBannerVisible && migratePending"
      class="term-alert term-mb-1"
      style="border-color: rgba(251, 146, 60, 0.55); background: rgba(251, 146, 60, 0.08); color: var(--accent, #fb923c)"
    >
      <div>
        Перенос <strong>«{{ migratePending.deployment }}»</strong> →
        <strong>{{ migratePending.targetNode }}</strong>
      </div>
      <p class="term-text-dim term-fs-2xs term-mt-1" style="margin: 0;">
        <template v-if="migrateInFlight">Отправка запроса…</template>
        <template v-else>Ожидание готовности деплоймента на целевой ноде.</template>
      </p>
    </div>

    <div v-if="showSkeleton" class="term-card">Загрузка...</div>

    <div
      v-if="showLaunchModal"
      class="term-modal-overlay"
      @click.self="closeLaunchModal()"
    >
      <div class="term-modal">
        <h3 style="font-size: 1rem; margin: 0 0 0.75rem 0;">Запуск пода</h3>
        <p class="term-text-dim term-fs-2xs term-mb-1" style="margin-top: 0;">
          Образ контейнера выбирается на сервере по архитектуре ноды (amd64 / arm64).
        </p>
        <label class="term-fs-2xs term-text-dim" style="display: block; margin-bottom: 0.25rem;">Тип пода</label>
        <select
          v-model="selectedPresetId"
          class="term-btn term-mb-1"
          style="width: 100%; box-sizing: border-box; font-size: var(--fs-2xs);"
        >
          <option v-if="!computePresets.length" value="">Нет пресетов — проверьте API</option>
          <option
            v-for="p in computePresets"
            :key="p.id"
            :value="p.id"
          >
            {{ p.display_name }}
          </option>
        </select>
        <label
          class="term-fs-2xs"
          style="display: flex; align-items: center; gap: 0.35rem; margin-bottom: 0.75rem; cursor: pointer;"
        >
          <input v-model="autoOrchestrate" type="checkbox" />
          <span>Автоматическая оркестрация вычислений</span>
        </label>
        <label class="term-fs-2xs term-text-dim" style="display: block; margin-bottom: 0.25rem;">Нода</label>
        <select
          v-model="selectedNodeHostname"
          class="term-btn term-mb-1"
          style="width: 100%; box-sizing: border-box; font-size: var(--fs-2xs);"
          :disabled="autoOrchestrate"
        >
          <option v-if="!sortedPoolNodes.length" value="">Нет нод в пуле</option>
          <option
            v-for="n in sortedPoolNodes"
            :key="n.name"
            :value="n.name"
            :disabled="!n.ready"
          >
            {{ n.name }} — {{ n.labels['wolfpack.io/role'] || '—' }} · {{ n.architecture }} ·
            {{ n.ready ? 'Ready' : 'NotReady' }}
          </option>
        </select>
        <div style="display: flex; gap: 0.5rem;">
          <button type="button" class="term-btn" style="flex: 1;" @click="closeLaunchModal()">
            Отмена
          </button>
          <button
            type="button"
            class="term-btn"
            style="flex: 1;"
            :disabled="
              launchInFlight ||
                !selectedPresetId ||
                (!autoOrchestrate && !selectedNodeHostname)
            "
            @click="confirmLaunch()"
          >
            {{ launchInFlight ? 'Запуск…' : 'Запустить' }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="!showSkeleton"
      class="term-card orchestration-card"
      :class="{ 'orchestration-card--refresh': refreshing }"
    >
      <div
        v-if="orphanPods.length"
        class="term-mb-1"
        style="border: 1px dashed var(--accent); border-radius: 6px; padding: 0.75rem;"
      >
        <h3 style="margin: 0 0 0.35rem 0; font-size: 1rem;">Поды вне пула ресурсов</h3>
        <div style="display: flex; flex-wrap: wrap; gap: 0.35rem;">
          <div
            v-for="pod in orphanPods"
            :key="pod.name"
            class="orchestration-pod-chip term-btn"
          >
            <span
              :draggable="!interactionLocked && !!pod.deploymentName"
              class="orchestration-pod-chip__drag"
              :title="`${pod.deploymentName || pod.name} @ ${pod.nodeName || '?'}`"
              @dragstart="onDragStart(pod.deploymentName, pod.name, $event)"
              @dragend="onDragEnd"
            >
              {{ pod.deploymentName || pod.name }}
              <span class="term-text-dim"> @{{ pod.nodeName }}</span>
            </span>
            <button
              v-if="pod.deploymentName"
              type="button"
              class="orchestration-pod-chip__close"
              :disabled="interactionLocked"
              title="Остановить под (deployment → 0 реплик)"
              @click.stop.prevent="onStopDeployment(pod.deploymentName)"
            >
              ×
            </button>
          </div>
        </div>
      </div>
      <div
        v-for="node in sortedPoolNodes"
        :key="node.name"
        class="term-mb-1 orchestration-node-drop"
        style="border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem;"
        :class="{ 'orchestration-node-drop--active': migratePending?.targetNode === node.name }"
        @dragover.prevent
        @drop="onDropNode(node.name, $event)"
      >
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <h3 style="margin: 0; font-size: 1rem;">
            {{ node.name }}
            <span class="term-text-dim term-fs-2xs">
              {{ node.labels['wolfpack.io/role'] || '—' }} · {{ node.architecture }} ·
              {{ node.ready ? 'Ready' : 'NotReady' }}
            </span>
          </h3>
        </div>
        <div style="margin-top: 0.5rem; min-height: 2rem; display: flex; flex-wrap: wrap; gap: 0.35rem;">
          <div
            v-for="pod in (podsByNode[node.name] || [])"
            :key="pod.name"
            class="orchestration-pod-chip term-btn"
            :title="pod.deploymentName || pod.name"
          >
            <span
              :draggable="!interactionLocked && !!pod.deploymentName"
              class="orchestration-pod-chip__drag"
              @dragstart="onDragStart(pod.deploymentName, pod.name, $event)"
              @dragend="onDragEnd"
            >
              {{ pod.deploymentName || pod.name }}
            </span>
            <button
              v-if="pod.deploymentName"
              type="button"
              class="orchestration-pod-chip__close"
              :disabled="interactionLocked"
              title="Остановить под (deployment → 0 реплик)"
              @click.stop.prevent="onStopDeployment(pod.deploymentName)"
            >
              ×
            </button>
          </div>
          <span v-if="!(podsByNode[node.name]?.length)" class="term-text-dim term-fs-2xs">нет подов</span>
        </div>
      </div>
    </div>
  </DefaultLayout>
</template>

<style scoped>
.orchestration-card {
  transition: opacity 0.15s ease;
}
.orchestration-card--refresh {
  opacity: 0.88;
  pointer-events: none;
}
.orchestration-node-drop--active {
  outline: 2px solid rgba(251, 146, 60, 0.65);
  outline-offset: 2px;
}

.orchestration-title-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
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
  max-width: 26rem;
  width: calc(100% - 2rem);
}

.orchestration-pod-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  font-size: var(--fs-2xs);
  padding: 0.2rem 0.35rem 0.2rem 0.45rem;
}

.orchestration-pod-chip__drag {
  cursor: grab;
  flex: 1;
  min-width: 0;
}

.orchestration-pod-chip__close {
  flex-shrink: 0;
  width: 1.35rem;
  height: 1.35rem;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted, #888);
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.orchestration-pod-chip__close:hover:not(:disabled) {
  color: var(--accent, #fb923c);
  background: rgba(251, 146, 60, 0.12);
}

.orchestration-pod-chip__close:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
