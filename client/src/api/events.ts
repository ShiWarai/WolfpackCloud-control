import apiClient from './client'

export interface DeploymentEvent {
  id: number
  deployment: string
  from_host: string | null
  to_host: string | null
  status: string
  user_id: number | null
  preset_id: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export const eventsApi = {
  async listDeployments(
    limit = 200,
    status?: string,
    deployment?: string,
  ): Promise<DeploymentEvent[]> {
    const res = await apiClient.get<DeploymentEvent[]>('/events/deployments', {
      params: { limit, status, deployment },
    })
    return res.data
  },
}
