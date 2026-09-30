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
  memory_request_mib: number
  cpu_request_millicores: number
}

export interface ComputePresetLaunchBody {
  node_hostname?: string | null
  auto_orchestrate: boolean
}

export interface OrchestrationStep {
  id: string
  name: string
  formula: string
}

export interface OrchestrationNodeTrace {
  name: string
  ready: boolean
  architecture: string
  f1_passed: boolean
  f1_reason?: string | null
  q_ram?: number | null
  q_cpu?: number | null
  barrier_passed?: boolean | null
  f?: number | null
  latency_ms?: number | null
  selected: boolean
}

export interface OrchestrationRankingEntry {
  node_hostname: string
  f: number
  latency_ms: number
}

export interface OrchestrationTask {
  memory_request_mib: number
  cpu_request_millicores: number
  weight_ram: number
  weight_cpu: number
}

export interface OrchestrationTrace {
  steps: OrchestrationStep[]
  nodes: OrchestrationNodeTrace[]
  chosen?: string | null
  ranking: OrchestrationRankingEntry[]
  task?: OrchestrationTask | null
  error?: string | null
}

export interface ComputePresetLaunchResult {
  ok: boolean
  preset_id: string
  deployment_name: string
  node_hostname: string
  architecture: string
  image: string
  orchestration_trace?: OrchestrationTrace | null
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
