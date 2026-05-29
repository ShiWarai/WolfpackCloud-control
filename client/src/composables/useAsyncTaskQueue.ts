import { computed, ref, type Ref } from 'vue'

export type TaskStatus = 'queued' | 'running' | 'done' | 'failed'

export interface AsyncTask<TMeta> {
  id: string
  key: string
  status: TaskStatus
  meta: TMeta
  error?: string
  enqueuedAt: number
}

interface PendingTask<TMeta> {
  id: string
  key: string
  meta: TMeta
  enqueuedAt: number
  fn: () => Promise<void>
  settle: (err?: unknown) => void
}

export interface UseAsyncTaskQueueOptions {
  maxConcurrent?: number
  doneTtlMs?: number
}

let taskSeq = 0

function nextTaskId(): string {
  taskSeq += 1
  return `task-${taskSeq}`
}

/** Очередь async-задач: параллельность между разными key, сериализация внутри одного key. */
export function useAsyncTaskQueue<TMeta>(options: UseAsyncTaskQueueOptions = {}) {
  const maxConcurrent = options.maxConcurrent ?? 4
  const doneTtlMs = options.doneTtlMs ?? 5000

  const tasks = ref<AsyncTask<TMeta>[]>([]) as Ref<AsyncTask<TMeta>[]>
  const pending: PendingTask<TMeta>[] = []
  const runningKeys = new Set<string>()
  let runningCount = 0
  const removeTimers = new Map<string, ReturnType<typeof setTimeout>>()

  function upsertTask(task: AsyncTask<TMeta>) {
    const idx = tasks.value.findIndex((t) => t.id === task.id)
    if (idx === -1) tasks.value.push(task)
    else tasks.value[idx] = task
  }

  function scheduleRemove(taskId: string) {
    const existing = removeTimers.get(taskId)
    if (existing) clearTimeout(existing)
    removeTimers.set(
      taskId,
      setTimeout(() => {
        removeTimers.delete(taskId)
        tasks.value = tasks.value.filter((t) => t.id !== taskId)
      }, doneTtlMs),
    )
  }

  function tryRunNext() {
    while (runningCount < maxConcurrent && pending.length > 0) {
      const idx = pending.findIndex((task) => !runningKeys.has(task.key))
      if (idx === -1) break

      const [next] = pending.splice(idx, 1)
      startTask(next)
    }
  }

  function startTask(pendingTask: PendingTask<TMeta>) {
    runningCount += 1
    runningKeys.add(pendingTask.key)
    upsertTask({
      id: pendingTask.id,
      key: pendingTask.key,
      status: 'running',
      meta: pendingTask.meta,
      enqueuedAt: pendingTask.enqueuedAt,
    })

    void pendingTask
      .fn()
      .then(() => {
        upsertTask({
          id: pendingTask.id,
          key: pendingTask.key,
          status: 'done',
          meta: pendingTask.meta,
          enqueuedAt: pendingTask.enqueuedAt,
        })
        pendingTask.settle()
        scheduleRemove(pendingTask.id)
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : 'Ошибка задачи'
        upsertTask({
          id: pendingTask.id,
          key: pendingTask.key,
          status: 'failed',
          meta: pendingTask.meta,
          error: message,
          enqueuedAt: pendingTask.enqueuedAt,
        })
        pendingTask.settle(err)
        scheduleRemove(pendingTask.id)
      })
      .finally(() => {
        runningCount -= 1
        runningKeys.delete(pendingTask.key)
        tryRunNext()
      })
  }

  function enqueue(key: string, fn: () => Promise<void>, meta: TMeta): Promise<void> {
    return new Promise((resolve, reject) => {
      const id = nextTaskId()
      const enqueuedAt = Date.now()
      const pendingTask: PendingTask<TMeta> = {
        id,
        key,
        meta,
        enqueuedAt,
        fn,
        settle: (err) => {
          if (err !== undefined) reject(err)
          else resolve()
        },
      }

      upsertTask({ id, key, status: 'queued', meta, enqueuedAt })
      pending.push(pendingTask)
      tryRunNext()
    })
  }

  function isKeyBusy(key: string): boolean {
    if (runningKeys.has(key)) return true
    return pending.some((task) => task.key === key)
  }

  function clearDone() {
    for (const [taskId, timer] of removeTimers.entries()) {
      clearTimeout(timer)
      removeTimers.delete(taskId)
    }
    tasks.value = tasks.value.filter((t) => t.status === 'queued' || t.status === 'running')
  }

  const activeTasks = computed(() =>
    tasks.value.filter((t) => t.status === 'queued' || t.status === 'running'),
  )

  return {
    tasks,
    activeTasks,
    enqueue,
    isKeyBusy,
    clearDone,
  }
}
