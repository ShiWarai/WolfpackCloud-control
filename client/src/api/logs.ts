import apiClient from './client'

export interface RosLogEntry {
  id: number
  network_id: number | null
  ros_node_name: string | null
  level: string | null
  message: string
  recorded_at: string
}

export interface LogsStatus {
  influxdb: 'connected' | 'disabled' | 'error'
  rosout_bridge: 'running' | 'not_running' | 'unknown'
  message: string | null
}

export const logsApi = {
  async getStatus(): Promise<LogsStatus> {
    const res = await apiClient.get<LogsStatus>('/logs/status')
    return res.data
  },

  async list(networkId?: number, limit = 200): Promise<RosLogEntry[]> {
    const res = await apiClient.get<RosLogEntry[]>('/logs', {
      params: { network_id: networkId, limit },
    })
    return res.data
  },
}
