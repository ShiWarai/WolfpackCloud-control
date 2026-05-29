import { computed, ref } from 'vue'

import { clusterApi } from '@/api/cluster'
import type { ClusterPod, OrchestrationResponse } from '@/api/cluster'
import { workloadsApi } from '@/api/workloads'

import { useAsyncTaskQueue } from './useAsyncTaskQueue'

export type OrchestrationTaskKind = 'migrate' | 'stop'

export interface OrchestrationTaskMeta {
  kind: OrchestrationTaskKind
  deployment: string
  targetNode?: string
}

export interface MigrationWatch {
  deployment: string
  targetNode: string
  startedAt: number
}

export interface OrchestrationTasksContext {
  deployments: () => OrchestrationResponse['deployments']
  podsByNode: () => Record<string, ClusterPod[]>
  orphanPods: () => ClusterPod[]
  onTaskComplete: () => void | Promise<void>
  onError: (message: string) => void
  onSuccess: (message: string) => void
}

const MIGRATE_WATCH_MAX_MS = 15 * 60 * 1000
const NODE_HOSTNAME_SELECTOR = 'kubernetes.io/hostname'

function formatApiError(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: string }; status?: number } }
  const detail = e.response?.data?.detail
  if (e.response?.status === 403) return detail || 'Недостаточно прав.'
  if (e.response?.status === 404) return detail || 'Deployment не найден или недоступен.'
  return detail || fallback
}

export function useOrchestrationTasks(ctx: OrchestrationTasksContext) {
  const queue = useAsyncTaskQueue<OrchestrationTaskMeta>({ maxConcurrent: 4 })
  const migrationWatches = ref<Map<string, MigrationWatch>>(new Map())

  function podsMatchingDeployment(deploymentName: string): ClusterPod[] {
    const out: ClusterPod[] = []
    for (const list of Object.values(ctx.podsByNode())) {
      for (const p of list) {
        if (p.deploymentName === deploymentName) out.push(p)
      }
    }
    for (const p of ctx.orphanPods()) {
      if (p.deploymentName === deploymentName) out.push(p)
    }
    return out
  }

  function tryFinishMigrationWatches() {
    if (!migrationWatches.value.size) return

    const next = new Map(migrationWatches.value)
    for (const [deployment, watch] of migrationWatches.value.entries()) {
      if (Date.now() - watch.startedAt > MIGRATE_WATCH_MAX_MS) {
        next.delete(deployment)
        continue
      }

      const dep = ctx.deployments().find((d) => d.name === deployment)
      if (dep) {
        const sel = dep.nodeSelector || {}
        const onTarget = sel[NODE_HOSTNAME_SELECTOR] === watch.targetNode
        const want = dep.replicas ?? 0
        const ready = dep.readyReplicas ?? 0
        if (onTarget && want > 0 && ready >= want) {
          next.delete(deployment)
          continue
        }
      }

      const pods = podsMatchingDeployment(deployment)
      if (
        pods.length > 0 &&
        pods.every(
          (p) =>
            p.nodeName === watch.targetNode &&
            (p.phase === 'Running' || p.phase === 'Succeeded'),
        )
      ) {
        next.delete(deployment)
      }
    }

    if (next.size !== migrationWatches.value.size) {
      migrationWatches.value = next
    }
  }

  function isDeploymentBusy(deploymentName: string | undefined): boolean {
    if (!deploymentName) return false
    return queue.isKeyBusy(deploymentName) || migrationWatches.value.has(deploymentName)
  }

  function isDeploymentWatching(deploymentName: string | undefined): boolean {
    if (!deploymentName) return false
    return migrationWatches.value.has(deploymentName)
  }

  const activeMigrations = computed(() => [...migrationWatches.value.values()])

  const migrateBannerVisible = computed(
    () =>
      activeMigrations.value.length > 0 ||
      queue.tasks.value.some(
        (t) =>
          t.meta.kind === 'migrate' &&
          (t.status === 'queued' || t.status === 'running'),
      ),
  )

  function isMigrateRunning(deployment: string): boolean {
    return queue.tasks.value.some(
      (t) =>
        t.key === deployment &&
        t.meta.kind === 'migrate' &&
        t.status === 'running',
    )
  }

  async function enqueueMigrate(deployment: string, targetNode: string) {
    if (isDeploymentBusy(deployment)) return

    try {
      await queue.enqueue(
        deployment,
        async () => {
          await workloadsApi.migrateByDeploymentName(deployment, targetNode)
          const next = new Map(migrationWatches.value)
          next.set(deployment, {
            deployment,
            targetNode,
            startedAt: Date.now(),
          })
          migrationWatches.value = next
          ctx.onSuccess(`Перенос запущен: «${deployment}» → ${targetNode}`)
          await ctx.onTaskComplete()
        },
        { kind: 'migrate', deployment, targetNode },
      )
    } catch (err: unknown) {
      const next = new Map(migrationWatches.value)
      next.delete(deployment)
      migrationWatches.value = next
      ctx.onError(formatApiError(err, 'Ошибка миграции'))
    }
  }

  async function enqueueStop(deployment: string) {
    if (isDeploymentBusy(deployment)) return

    try {
      await queue.enqueue(
        deployment,
        async () => {
          await clusterApi.stopDeployment(deployment)
          ctx.onSuccess(`Остановлен деплоймент «${deployment}»`)
          await ctx.onTaskComplete()
        },
        { kind: 'stop', deployment },
      )
    } catch (err: unknown) {
      ctx.onError(formatApiError(err, 'Не удалось остановить деплоймент'))
    }
  }

  return {
    tasks: queue.tasks,
    activeTasks: queue.activeTasks,
    migrationWatches,
    activeMigrations,
    migrateBannerVisible,
    isDeploymentBusy,
    isDeploymentWatching,
    isMigrateRunning,
    tryFinishMigrationWatches,
    enqueueMigrate,
    enqueueStop,
    triggerRefresh: () => ctx.onTaskComplete(),
  }
}
