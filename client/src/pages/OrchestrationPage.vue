<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { clusterApi } from '@/api/cluster'
import type {
  ClusterPod,
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
  () => migrateInFlight.value || refreshing.value,
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
      <button
        type="button"
        class="term-btn"
        :disabled="interactionLocked"
        @click="load()"
      >
        {{ refreshing ? 'Обновление…' : 'Обновить' }}
      </button>
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
        <template v-else>
          Ожидание готовности деплоймента на целевой ноде (список обновляется каждые {{ POLL_MS / 1000 }} с без моргания).
        </template>
      </p>
    </div>

    <div v-if="showSkeleton" class="term-card">Загрузка...</div>

    <div
      v-else
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
            :draggable="!interactionLocked"
            class="term-btn"
            style="cursor: grab; font-size: var(--fs-2xs); padding: 0.25rem 0.5rem;"
            :title="`${pod.deploymentName || pod.name} @ ${pod.nodeName || '?'}`"
            @dragstart="onDragStart(pod.deploymentName, pod.name, $event)"
            @dragend="onDragEnd"
          >
            {{ pod.deploymentName || pod.name }}
            <span class="term-text-dim"> @{{ pod.nodeName }}</span>
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
            :draggable="!interactionLocked"
            class="term-btn"
            style="cursor: grab; font-size: var(--fs-2xs); padding: 0.25rem 0.5rem;"
            :title="pod.deploymentName || pod.name"
            @dragstart="onDragStart(pod.deploymentName, pod.name, $event)"
            @dragend="onDragEnd"
          >
            {{ pod.deploymentName || pod.name }}
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
</style>
