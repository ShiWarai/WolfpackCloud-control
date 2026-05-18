import apiClient from './client'

export const workloadsApi = {
  /** Свои workloads из БД Control — любой пользователь с доступом к записи. */
  async migrateOwnedWorkload(deploymentName: string, nodeHostname: string | null) {
    await apiClient.post(`/workloads/${encodeURIComponent(deploymentName)}/migrate`, {
      node_hostname: nodeHostname,
    })
  },

  /** Произвольный Deployment в namespace zenoh — любой залогиненный пользователь (кроме защищённых имён). */
  async migrateByDeploymentName(deploymentName: string, nodeHostname: string | null) {
    await apiClient.post(`/workloads/by-name/${encodeURIComponent(deploymentName)}/migrate`, {
      node_hostname: nodeHostname,
    })
  },
}
