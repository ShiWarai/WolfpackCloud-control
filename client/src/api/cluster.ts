import apiClient from './client'

export interface WorkerNode {
  name: string
  ready: boolean
  architecture: string
  labels: Record<string, string>
}

export interface ClusterPod {
  name: string
  phase: string | undefined
  nodeName: string | undefined
  deploymentName?: string
  labels: Record<string, string>
}

export interface OrchestrationResponse {
  workerNodes: WorkerNode[]
  podsByNode: Record<string, ClusterPod[]>
  /** Поды на нодах вне пула ролей (см. K8S_RESOURCE_POOL_ROLE_VALUES на API) или без nodeName */
  orphanPods: ClusterPod[]
  deployments: Array<{
    name: string
    replicas: number
    readyReplicas: number
    nodeSelector: Record<string, string>
    labels: Record<string, string>
  }>
}

export interface ComputePreset {
  id: string
  deployment_name: string
  display_name: string
  publish_topic: string
  subscribe_topic: string
  peer_shard: number
}

export interface ComputePresetLaunchBody {
  node_hostname?: string | null
  auto_orchestrate: boolean
}

export interface ComputePresetLaunchResult {
  ok: boolean
  preset_id: string
  deployment_name: string
  node_hostname: string
  architecture: string
  image: string
}

export const clusterApi = {
  async getOrchestration(): Promise<OrchestrationResponse> {
    const res = await apiClient.get<OrchestrationResponse>('/cluster/orchestration')
    return res.data
  },

  async getComputePresets(): Promise<ComputePreset[]> {
    const res = await apiClient.get<ComputePreset[]>('/cluster/compute-presets')
    return res.data
  },

  async launchComputePreset(
    presetId: string,
    body: ComputePresetLaunchBody,
  ): Promise<ComputePresetLaunchResult> {
    const res = await apiClient.post<ComputePresetLaunchResult>(
      `/cluster/compute-presets/${encodeURIComponent(presetId)}/launch`,
      body,
    )
    return res.data
  },

  async stopDeployment(deploymentName: string): Promise<{ ok: boolean; deployment: string; replicas: number }> {
    const res = await apiClient.post(`/cluster/deployments/${encodeURIComponent(deploymentName)}/stop`)
    return res.data
  },
}
