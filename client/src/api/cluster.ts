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

export const clusterApi = {
  async getOrchestration(): Promise<OrchestrationResponse> {
    const res = await apiClient.get<OrchestrationResponse>('/cluster/orchestration')
    return res.data
  },
}
