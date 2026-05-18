import apiClient from './client'
import type { User } from '@/types'

export const authApi = {
  async getMe(): Promise<User> {
    const response = await apiClient.get<User>('/auth/me')
    return response.data
  },
}
