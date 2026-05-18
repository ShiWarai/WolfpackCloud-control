import apiClient from './client'

export interface RosLogEntry {
  id: number
  network_id: number | null
  ros_node_name: string | null
  level: string | null
  message: string
  recorded_at: string
}

export const logsApi = {
  async list(networkId?: number, limit = 200): Promise<RosLogEntry[]> {
    const res = await apiClient.get<RosLogEntry[]>('/logs', {
      params: { network_id: networkId, limit },
    })
    return res.data
  },
}
