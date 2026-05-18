import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { robotsApi, type RobotListParams } from '@/api/robots'
import type { Robot, RobotDetail, RobotUpdate, RobotStatus } from '@/types'

export const useRobotsStore = defineStore('robots', () => {
  const robots = ref<Robot[]>([])
  const currentRobot = ref<RobotDetail | null>(null)
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeRobots = computed(() => 
    robots.value.filter(r => r.status === 'active')
  )

  const pendingRobots = computed(() => 
    robots.value.filter(r => r.status === 'pending')
  )

  const robotsByStatus = computed(() => {
    const statuses: Record<RobotStatus, number> = {
      active: 0,
      pending: 0,
      inactive: 0,
      error: 0,
    }
    robots.value.forEach(r => {
      statuses[r.status]++
    })
    return statuses
  })

  async function fetchRobots(params?: RobotListParams) {
    loading.value = true
    error.value = null
    try {
      const response = await robotsApi.list(params)
      robots.value = response.robots
      total.value = response.total
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      error.value = err.response?.data?.detail || 'Ошибка загрузки роботов'
    } finally {
      loading.value = false
    }
  }

  async function fetchRobot(id: number) {
    loading.value = true
    error.value = null
    try {
      currentRobot.value = await robotsApi.get(id)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      error.value = err.response?.data?.detail || 'Ошибка загрузки робота'
    } finally {
      loading.value = false
    }
  }

  async function updateRobot(id: number, data: RobotUpdate) {
    loading.value = true
    error.value = null
    try {
      const updated = await robotsApi.update(id, data)
      const index = robots.value.findIndex(r => r.id === id)
      if (index !== -1) {
        robots.value[index] = updated
      }
      if (currentRobot.value?.id === id) {
        currentRobot.value = { ...currentRobot.value, ...updated }
      }
      return updated
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      error.value = err.response?.data?.detail || 'Ошибка обновления робота'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deleteRobot(id: number) {
    loading.value = true
    error.value = null
    try {
      await robotsApi.delete(id)
      robots.value = robots.value.filter(r => r.id !== id)
      total.value--
      if (currentRobot.value?.id === id) {
        currentRobot.value = null
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      error.value = err.response?.data?.detail || 'Ошибка удаления робота'
      throw e
    } finally {
      loading.value = false
    }
  }

  function clearCurrent() {
    currentRobot.value = null
  }

  return {
    robots,
    currentRobot,
    total,
    loading,
    error,
    activeRobots,
    pendingRobots,
    robotsByStatus,
    fetchRobots,
    fetchRobot,
    updateRobot,
    deleteRobot,
    clearCurrent,
  }
})
