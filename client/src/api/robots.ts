import apiClient from './client'
import type { Robot, RobotDetail, RobotListResponse, RobotStatus, RobotUpdate } from '@/types'

export interface RobotListParams {
  status?: RobotStatus
  search?: string
  skip?: number
  limit?: number
}

export const robotsApi = {
  async list(params?: RobotListParams): Promise<RobotListResponse> {
    const response = await apiClient.get<RobotListResponse>('/robots', { params })
    return response.data
  },

  async get(id: number): Promise<RobotDetail> {
    const response = await apiClient.get<RobotDetail>(`/robots/${id}`)
    return response.data
  },

  async update(id: number, data: RobotUpdate): Promise<Robot> {
    const response = await apiClient.patch<Robot>(`/robots/${id}`, data)
    return response.data
  },

  async delete(id: number): Promise<void> {
    await apiClient.delete(`/robots/${id}`)
  },

  async heartbeat(id: number): Promise<Robot> {
    const response = await apiClient.post<Robot>(`/robots/${id}/heartbeat`)
    return response.data
  },
}
