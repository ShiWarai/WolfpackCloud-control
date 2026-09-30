import apiClient from './client'
import type { PairCodeInfo, PairConfirmResponse } from '@/types'

export const pairingApi = {
  async getCodeInfo(code: string): Promise<PairCodeInfo> {
    const response = await apiClient.get<PairCodeInfo>(`/pair/${code}`)
    return response.data
  },

  async confirm(code: string, robotName?: string): Promise<PairConfirmResponse> {
    const response = await apiClient.post<PairConfirmResponse>(`/pair/${code}/confirm`, {
      robot_name: robotName,
    })
    return response.data
  },
}
