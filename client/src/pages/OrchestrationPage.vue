<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { clusterApi } from '@/api/cluster'
import type {
  ClusterPod,
  ComputePreset,
  OrchestrationResponse,
  OrchestrationTrace,
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

const DRAG_START_THRESHOLD_PX = 10

const dragState = ref<{
  deploymentName: string
  podName: string
  pointerId: number
  startX: number
  startY: number
} | null>(null)
const dragActive = ref(false)
const dragGhostPos = ref({ x: 0, y: 0 })
const dragOverNode = ref<string | null>(null)

const dragGhostLabel = computed(() => dragState.value?.deploymentName ?? '')
const showDragGhost = computed(() => dragActive.value && !!dragState.value)

const AUTO_ORCHESTRATION_BLOCK_LABEL = 'wolfpack.io/auto-orchestration'
const AUTO_ORCHESTRATION_BLOCK_VALUE = 'blocked'

const showLaunchModal = ref(false)
const launchInFlight = ref(false)
const launchSucceeded = ref(false)
const autoOrchestrate = ref(false)
const orchestrationTrace = ref<OrchestrationTrace | null>(null)
const showOrchestrationPanel = ref(false)
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

const launchModalWide = computed(
  () => showOrchestrationPanel.value || (autoOrchestrate.value && launchInFlight.value),
)

function isNodeAutoBlocked(n: WorkerNode): boolean {
  return n.labels[AUTO_ORCHESTRATION_BLOCK_LABEL] === AUTO_ORCHESTRATION_BLOCK_VALUE
}

const F1_REASON_LABELS: Record<string, string> = {
  auto_orchestration_blocked: 'заблокирована',
  not_ready: 'NotReady',
  bad_architecture: 'арх.',
  peer_image_not_configured: 'нет образа peer',
  robot_agent_image_not_configured: 'нет образа робота',
}

function formatF1Cell(node: OrchestrationTrace['nodes'][number]): string {
  if (node.f1_passed) return '✓'
  const reason = node.f1_reason ? F1_REASON_LABELS[node.f1_reason] || node.f1_reason : '✗'
  return `✗ ${reason}`
}

function formatQCell(node: OrchestrationTrace['nodes'][number]): string {
  if (node.q_ram == null && node.q_cpu == null) return '—'
  const ram = node.q_ram != null ? node.q_ram.toFixed(4) : '—'
  const cpu = node.q_cpu != null ? node.q_cpu.toFixed(4) : '—'
  return `${ram} / ${cpu}`
}

function formatBarrierCell(node: OrchestrationTrace['nodes'][number]): string {
  if (node.barrier_passed == null) return '—'
  return node.barrier_passed ? '✓' : '✗'
}

function formatFCell(node: OrchestrationTrace['nodes'][number]): string {
  if (node.f == null) return '—'
  return node.f.toFixed(4)
}

function traceStepHint(stepId: string): string {
  const step = orchestrationTrace.value?.steps.find((s) => s.id === stepId)
  if (!step) return ''
  return `${step.name}\n${step.formula}`
}

function resetLaunchTraceState() {
  orchestrationTrace.value = null
  showOrchestrationPanel.value = false
  launchSucceeded.value = false
}

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

function isPodMigrating(deploymentName: string | undefined): boolean {
  if (!deploymentName || !migratePending.value) return false
  return migratePending.value.deployment === deploymentName
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

function cleanupDragListeners() {
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', onWindowPointerUp)
  window.removeEventListener('pointercancel', onWindowPointerUp)
}

function resetDragState() {
  dragState.value = null
  dragActive.value = false
  dragOverNode.value = null
  dragged.value = null
}

function onWindowPointerMove(ev: PointerEvent) {
  if (!dragState.value || ev.pointerId !== dragState.value.pointerId) return

  if (!dragActive.value) {
    const dx = ev.clientX - dragState.value.startX
    const dy = ev.clientY - dragState.value.startY
    if (Math.hypot(dx, dy) < DRAG_START_THRESHOLD_PX) return
    dragActive.value = true
    dragged.value = {
      deploymentName: dragState.value.deploymentName,
      podName: dragState.value.podName,
    }
  }

  ev.preventDefault()
  dragGhostPos.value = { x: ev.clientX, y: ev.clientY }

  const under = document.elementFromPoint(ev.clientX, ev.clientY)
  const zone = under?.closest('[data-drop-node]') as HTMLElement | null
  const nodeName = zone?.dataset.dropNode
  if (!nodeName) {
    dragOverNode.value = null
    return
  }
  const node = workerNodes.value.find((n) => n.name === nodeName)
  dragOverNode.value = node?.ready ? nodeName : null
}

async function onWindowPointerUp(ev: PointerEvent) {
  if (!dragState.value || ev.pointerId !== dragState.value.pointerId) return

  cleanupDragListeners()

  const dep = dragState.value.deploymentName
  const targetNodeName = dragOverNode.value
  const wasDragging = dragActive.value

  resetDragState()

  if (!wasDragging || !targetNodeName) return
  const node = workerNodes.value.find((n) => n.name === targetNodeName)
  if (node) await migrateDeploymentToNode(node, dep)
}

function onPodPointerDown(dep: string | undefined, pod: string, ev: PointerEvent) {
  if (!dep || interactionLocked.value || isPodMigrating(dep)) return
  if (ev.pointerType === 'mouse' && ev.button !== 0) return

  resetDragState()
  dragState.value = {
    deploymentName: dep,
    podName: pod,
    pointerId: ev.pointerId,
    startX: ev.clientX,
    startY: ev.clientY,
  }

  window.addEventListener('pointermove', onWindowPointerMove, { passive: false })
  window.addEventListener('pointerup', onWindowPointerUp)
  window.addEventListener('pointercancel', onWindowPointerUp)
}

async function migrateDeploymentToNode(node: WorkerNode, dep: string) {
  if (!node.ready || interactionLocked.value || !dep) return
  migrateInFlight.value = true
  migratePending.value = {
    deployment: dep,
    targetNode: node.name,
    startedAt: Date.now(),
  }
  error.value = null
  try {
    await workloadsApi.migrateByDeploymentName(dep, node.name)
    await load({ quiet: true })
    flashSuccess(`Перенос запущен: «${dep}» → ${node.name}`)
  } catch (e: unknown) {
    migratePending.value = null
    const err = e as { response?: { data?: { detail?: string }; status?: number } }
    const detail = err.response?.data?.detail
    if (err.response?.status === 403) {
      error.value = detail || 'Недостаточно прав.'
    } else if (err.response?.status === 404) {
      error.value =
        detail ||
        'Deployment не найден в namespace или недоступен для переноса.'
    } else {
      error.value = detail || 'Ошибка миграции'
    }
  } finally {
    migrateInFlight.value = false
  }
}

async function openLaunchModal() {
  showLaunchModal.value = true
  resetLaunchTraceState()
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
  resetLaunchTraceState()
}

function onAutoOrchestrateChange() {
  if (!launchInFlight.value && !launchSucceeded.value) {
    resetLaunchTraceState()
  }
}

async function confirmLaunch() {
  if (launchSucceeded.value) {
    closeLaunchModal()
    return
  }
  if (!selectedPresetId.value) {
    error.value = 'Выберите тип пода'
    return
  }
  if (!autoOrchestrate.value && !selectedNodeHostname.value) {
    error.value = 'Выберите ноду или включите автоматическую оркестрацию'
    return
  }
  if (autoOrchestrate.value) {
    showOrchestrationPanel.value = true
    orchestrationTrace.value = null
  }
  launchInFlight.value = true
  error.value = null
  try {
    const r = await clusterApi.launchComputePreset(selectedPresetId.value, {
      node_hostname: autoOrchestrate.value ? null : selectedNodeHostname.value,
      auto_orchestrate: autoOrchestrate.value,
    })
    flashSuccess(`Запущено: «${r.deployment_name}» на ${r.node_hostname} (${r.architecture})`)
    if (autoOrchestrate.value) {
      orchestrationTrace.value = r.orchestration_trace ?? null
      launchSucceeded.value = true
      await load({ quiet: true })
    } else {
      showLaunchModal.value = false
      resetLaunchTraceState()
      await load({ quiet: true })
    }
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
  cleanupDragListeners()
  resetDragState()
  if (successClearTimer) clearTimeout(successClearTimer)
})
</script>

<template>
  <DefaultLayout>
    <div class="term-page-title-row">
      <div class="orchestration-page-title">
        <h1 class="term-page-title" data-testid="orchestration-heading">Ресурсы кластера</h1>
        <span
          class="orchestration-hint"
          title="Перетащите (или удержите и перетащите на телефоне) карточку пода на ноду пула (только Ready)."
        >?</span>
      </div>
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
      <div
        class="term-modal"
        :class="{ 'term-modal--orchestration': launchModalWide }"
      >
        <h3 style="font-size: 1rem; margin: 0 0 0.75rem 0;">Запуск пода</h3>
        <div
          class="term-modal__body"
          :class="{ 'term-modal__body--split': launchModalWide }"
        >
          <div class="term-modal__form">
            <p class="term-text-dim term-fs-2xs term-mb-1" style="margin-top: 0;">
              Образ контейнера выбирается на сервере по архитектуре ноды (amd64 / arm64).
            </p>
            <label class="term-fs-2xs term-text-dim" style="display: block; margin-bottom: 0.25rem;">Тип пода</label>
            <select
              v-model="selectedPresetId"
              class="term-btn term-mb-1"
              style="width: 100%; box-sizing: border-box; font-size: var(--fs-2xs);"
              :disabled="launchInFlight || launchSucceeded"
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
              <input
                v-model="autoOrchestrate"
                type="checkbox"
                :disabled="launchInFlight || launchSucceeded"
                @change="onAutoOrchestrateChange()"
              />
              <span>Автоматическая оркестрация вычислений</span>
            </label>
            <label class="term-fs-2xs term-text-dim" style="display: block; margin-bottom: 0.25rem;">Нода</label>
            <select
              v-model="selectedNodeHostname"
              class="term-btn term-mb-1"
              style="width: 100%; box-sizing: border-box; font-size: var(--fs-2xs);"
              :disabled="autoOrchestrate || launchInFlight || launchSucceeded"
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
                <template v-if="isNodeAutoBlocked(n)"> · авто: заблокирована</template>
              </option>
            </select>
            <div style="display: flex; gap: 0.5rem;">
              <button
                type="button"
                class="term-btn"
                style="flex: 1;"
                :disabled="launchInFlight"
                @click="closeLaunchModal()"
              >
                Отмена
              </button>
              <button
                type="button"
                class="term-btn"
                style="flex: 1;"
                :disabled="
                  launchInFlight ||
                    (!launchSucceeded && !selectedPresetId) ||
                    (!launchSucceeded && !autoOrchestrate && !selectedNodeHostname)
                "
                @click="confirmLaunch()"
              >
                {{
                  launchInFlight
                    ? 'Запуск…'
                    : launchSucceeded
                      ? 'Закрыть'
                      : 'Запустить'
                }}
              </button>
            </div>
          </div>

          <div v-if="showOrchestrationPanel" class="term-modal__trace">
            <h4 class="term-modal__trace-title">
              Расчёт авто-оркестрации
              <span
                class="orchestration-hint"
                title="Этапы: f1 (статический отсев) → q (запас RAM/CPU) → барьер → f (скоринг). Наведите на ? в заголовках колонок."
              >?</span>
            </h4>
            <p v-if="launchInFlight" class="term-text-dim term-fs-2xs">Расчёт…</p>
            <template v-else-if="orchestrationTrace">
              <div class="term-modal__trace-table-wrap">
                <table class="term-table term-modal__trace-table">
                  <thead>
                    <tr>
                      <th>Нода</th>
                      <th>
                        <span class="term-modal__trace-th">f1</span>
                        <span class="orchestration-hint" :title="traceStepHint('f1')">?</span>
                      </th>
                      <th>
                        <span class="term-modal__trace-th">q</span>
                        <span class="orchestration-hint" :title="traceStepHint('q')">?</span>
                      </th>
                      <th>
                        <span class="term-modal__trace-th">Барьер</span>
                        <span class="orchestration-hint" :title="traceStepHint('barrier')">?</span>
                      </th>
                      <th>
                        <span class="term-modal__trace-th">f</span>
                        <span class="orchestration-hint" :title="traceStepHint('f')">?</span>
                      </th>
                      <th>✓</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="node in orchestrationTrace.nodes"
                      :key="node.name"
                      :class="{ 'orchestration-trace-row--selected': node.selected }"
                    >
                      <td class="term-modal__trace-node" :title="node.name">{{ node.name }}</td>
                      <td>{{ formatF1Cell(node) }}</td>
                      <td>{{ formatQCell(node) }}</td>
                      <td>{{ formatBarrierCell(node) }}</td>
                      <td>{{ formatFCell(node) }}</td>
                      <td>{{ node.selected ? '✓' : '' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>
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
            :class="{ 'orchestration-pod-chip--migrating': isPodMigrating(pod.deploymentName) }"
          >
            <span
              class="orchestration-pod-chip__drag"
              :class="{
                'orchestration-pod-chip__drag--active': dragActive && dragged?.deploymentName === pod.deploymentName,
                'orchestration-pod-chip__drag--migrating': isPodMigrating(pod.deploymentName),
              }"
              :title="`${pod.deploymentName || pod.name} @ ${pod.nodeName || '?'}`"
              @pointerdown="onPodPointerDown(pod.deploymentName, pod.name, $event)"
            >
              <span
                v-if="isPodMigrating(pod.deploymentName)"
                class="orchestration-pod-chip__spinner"
                aria-hidden="true"
              />
              {{ pod.deploymentName || pod.name }}
              <span class="term-text-dim"> @{{ pod.nodeName }}</span>
            </span>
            <button
              v-if="pod.deploymentName"
              type="button"
              class="orchestration-pod-chip__close"
              :disabled="interactionLocked || isPodMigrating(pod.deploymentName)"
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
        :data-drop-node="node.name"
        :class="{
          'orchestration-node-drop--active': migratePending?.targetNode === node.name,
          'orchestration-node-drop--disabled': !node.ready,
          'orchestration-node-drop--drag-over': dragOverNode === node.name,
        }"
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
            :class="{ 'orchestration-pod-chip--migrating': isPodMigrating(pod.deploymentName) }"
            :title="pod.deploymentName || pod.name"
          >
            <span
              class="orchestration-pod-chip__drag"
              :class="{
                'orchestration-pod-chip__drag--active': dragActive && dragged?.deploymentName === pod.deploymentName,
                'orchestration-pod-chip__drag--migrating': isPodMigrating(pod.deploymentName),
              }"
              @pointerdown="onPodPointerDown(pod.deploymentName, pod.name, $event)"
            >
              <span
                v-if="isPodMigrating(pod.deploymentName)"
                class="orchestration-pod-chip__spinner"
                aria-hidden="true"
              />
              {{ pod.deploymentName || pod.name }}
            </span>
            <button
              v-if="pod.deploymentName"
              type="button"
              class="orchestration-pod-chip__close"
              :disabled="interactionLocked || isPodMigrating(pod.deploymentName)"
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

    <Teleport to="body">
      <div
        v-if="showDragGhost"
        class="orchestration-drag-ghost"
        :style="{ left: `${dragGhostPos.x}px`, top: `${dragGhostPos.y}px` }"
      >
        {{ dragGhostLabel }}
      </div>
    </Teleport>
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

.orchestration-node-drop--drag-over {
  border-color: var(--accent, #fb923c) !important;
  background: rgba(251, 146, 60, 0.08);
}

.orchestration-title-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.orchestration-page-title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.orchestration-hint {
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

.orchestration-hint:hover {
  color: var(--accent, #fb923c);
  border-color: rgba(251, 146, 60, 0.55);
}

.orchestration-node-drop--disabled {
  opacity: 0.42;
  border-style: dashed;
  border-color: rgba(128, 128, 128, 0.45);
  background: rgba(128, 128, 128, 0.06);
  cursor: not-allowed;
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

.term-modal--orchestration {
  max-width: min(72rem, calc(100vw - 1.5rem));
  width: calc(100% - 1.5rem);
}

.term-modal__body--split {
  display: flex;
  gap: 1.25rem;
  align-items: flex-start;
}

.term-modal__form {
  flex: 0 0 28%;
  min-width: 14rem;
}

.term-modal__trace {
  flex: 1 1 72%;
  min-width: 0;
  border-left: 1px solid var(--border);
  padding-left: 1rem;
}

.term-modal__trace-title {
  margin: 0 0 0.5rem 0;
  font-size: var(--fs-xs, 0.875rem);
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.term-modal__trace-th {
  margin-right: 0.15rem;
}

.term-modal__trace-table-wrap {
  overflow-x: auto;
}

.term-modal__trace-table {
  font-size: 0.625rem;
  line-height: 1.25;
  width: 100%;
}

.term-modal__trace-table th,
.term-modal__trace-table td {
  padding: 0.2rem 0.35rem;
  white-space: nowrap;
}

.term-modal__trace-table th {
  font-size: 0.65rem;
  font-weight: 600;
}

.term-modal__trace-node {
  max-width: 9rem;
  overflow: hidden;
  text-overflow: ellipsis;
}

.orchestration-trace-row--selected {
  background: rgba(251, 146, 60, 0.1);
}

@media (max-width: 640px) {
  .term-modal__body--split {
    flex-direction: column;
  }

  .term-modal__trace {
    border-left: none;
    border-top: 1px solid var(--border);
    padding-left: 0;
    padding-top: 1rem;
    width: 100%;
  }
}

.orchestration-pod-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  font-size: var(--fs-2xs);
  padding: 0.2rem 0.35rem 0.2rem 0.45rem;
}

.orchestration-pod-chip--migrating {
  border-color: rgba(251, 146, 60, 0.45);
  box-shadow: 0 0 0 1px rgba(251, 146, 60, 0.2);
}

.orchestration-pod-chip__drag {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  cursor: grab;
  flex: 1;
  min-width: 0;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}

.orchestration-pod-chip__drag--active {
  opacity: 0.45;
}

.orchestration-pod-chip__drag--migrating {
  cursor: wait;
  pointer-events: none;
}

.orchestration-pod-chip__spinner {
  display: inline-block;
  width: 0.85rem;
  height: 0.85rem;
  border: 2px solid rgba(251, 146, 60, 0.25);
  border-top-color: var(--accent, #fb923c);
  border-radius: 50%;
  animation: orchestration-pod-spin 0.75s linear infinite;
  flex-shrink: 0;
}

@keyframes orchestration-pod-spin {
  to {
    transform: rotate(360deg);
  }
}

.orchestration-drag-ghost {
  position: fixed;
  z-index: 400;
  pointer-events: none;
  transform: translate(-50%, -50%);
  padding: 0.35rem 0.65rem;
  border-radius: 6px;
  border: 1px solid var(--accent, #fb923c);
  background: var(--bg-card, #1a1a1a);
  color: var(--text);
  font-size: var(--fs-2xs);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  white-space: nowrap;
  max-width: min(16rem, calc(100vw - 2rem));
  overflow: hidden;
  text-overflow: ellipsis;
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
