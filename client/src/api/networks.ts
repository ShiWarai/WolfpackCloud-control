import apiClient from './client'

export interface Network {
  id: number
  name: string
  ros_domain_id: number
  owner_id: number
  created_at: string
  robot_count?: number
}

export interface NetworkCreateBody {
  name: string
  ros_domain_id: number
}

export const networksApi = {
  async list(): Promise<Network[]> {
    const res = await apiClient.get<Network[]>('/networks')
    return res.data
  },

  async create(body: NetworkCreateBody): Promise<Network> {
    const res = await apiClient.post<Network>('/networks', body)
    return res.data
  },

  async delete(id: number): Promise<void> {
    await apiClient.delete(`/networks/${id}`)
  },
}
