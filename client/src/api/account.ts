import apiClient from './client'
import type { Network } from './networks'
import type { User } from '@/types'

export interface AccountResponse {
  user: User
  keycloak_account_url: string
  networks: Network[]
}

export const accountApi = {
  async getAccount(): Promise<AccountResponse> {
    const res = await apiClient.get<AccountResponse>('/account')
    return res.data
  },
}
