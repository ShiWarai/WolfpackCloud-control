import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

import { keycloak } from '@/keycloak'

const API_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || '/api'

const apiClient: AxiosInstance = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    if (keycloak.authenticated && keycloak.token && config.headers) {
      try {
        await keycloak.updateToken(30)
      } catch {
        /* refresh failed — запрос уйдёт со старым токеном, ответ 401 обработает ниже */
      }
      config.headers.Authorization = `Bearer ${keycloak.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && keycloak.authenticated) {
      try {
        await keycloak.updateToken(30)
        const cfg = error.config
        if (cfg && keycloak.token) {
          cfg.headers.Authorization = `Bearer ${keycloak.token}`
          return apiClient(cfg)
        }
      } catch {
        await keycloak.login()
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
