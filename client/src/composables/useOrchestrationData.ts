import { ref } from 'vue'

import { clusterApi } from '@/api/cluster'
import type { ClusterPod, OrchestrationResponse } from '@/api/cluster'

import { useIntervalPoll } from './useIntervalPoll'

export function useOrchestrationData(onAfterLoad?: () => void) {
  const initialLoading = ref(true)
  const hasLoadedOnce = ref(false)
  const refreshing = ref(false)
  const error = ref<string | null>(null)

  const workerNodes = ref<OrchestrationResponse['workerNodes']>([])
  const podsByNode = ref<Record<string, ClusterPod[]>>({})
  const orphanPods = ref<ClusterPod[]>([])
  const deployments = ref<OrchestrationResponse['deployments']>([])

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
      onAfterLoad?.()
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

  const poll = useIntervalPoll({
    intervalMs: 5000,
    fetch: () => load({ quiet: true }),
    pauseWhenHidden: true,
    immediate: false,
  })

  return {
    initialLoading,
    hasLoadedOnce,
    refreshing,
    error,
    workerNodes,
    podsByNode,
    orphanPods,
    deployments,
    load,
    poll,
  }
}
