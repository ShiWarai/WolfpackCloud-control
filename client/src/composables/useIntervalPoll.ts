import { computed, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'

export interface UseIntervalPollOptions {
  intervalMs: number
  /** Возвращает true, когда polling должен быть активен. */
  enabled?: () => boolean
  fetch: (initial: boolean) => Promise<void>
  pauseWhenHidden?: boolean
  /** Debounce переключения enabled (мс). */
  enabledDebounceMs?: number
  /** Запускать сразу при mount, если enabled. */
  immediate?: boolean
}

/** Периодический quiet-poll с guard in-flight, visibility pause и triggerNow. */
export function useIntervalPoll(options: UseIntervalPollOptions) {
  const {
    intervalMs,
    fetch,
    pauseWhenHidden = true,
    enabledDebounceMs = 0,
    immediate = true,
  } = options

  const enabledFn = options.enabled ?? (() => true)

  let timer: ReturnType<typeof setInterval> | null = null
  let generation = 0
  let fetchInFlight: Promise<void> | null = null
  let enabledDebounceTimer: ReturnType<typeof setTimeout> | null = null
  let pausedByHidden = false

  const polling = ref(false)

  async function runFetch(initial: boolean) {
    if (!enabledFn() || pausedByHidden) return
    if (fetchInFlight) {
      if (!initial) return
      await fetchInFlight
    }

    const run = async () => {
      await fetch(initial)
    }

    fetchInFlight = run()
    try {
      await fetchInFlight
    } finally {
      fetchInFlight = null
    }
  }

  function stopTimer() {
    generation += 1
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    polling.value = false
  }

  async function startTimer() {
    stopTimer()
    if (!enabledFn() || pausedByHidden) return

    const gen = generation
    polling.value = true
    await runFetch(true)
    if (gen !== generation || !enabledFn() || pausedByHidden) {
      polling.value = false
      return
    }

    timer = setInterval(() => {
      void runFetch(false)
    }, intervalMs)
  }

  function scheduleEnabledChange() {
    if (enabledDebounceTimer) clearTimeout(enabledDebounceTimer)
    if (enabledDebounceMs <= 0) {
      if (enabledFn() && !pausedByHidden) void startTimer()
      else stopTimer()
      return
    }
    enabledDebounceTimer = setTimeout(() => {
      enabledDebounceTimer = null
      if (enabledFn() && !pausedByHidden) void startTimer()
      else stopTimer()
    }, enabledDebounceMs)
  }

  function onVisibilityChange() {
    if (!pauseWhenHidden) return
    if (document.hidden) {
      pausedByHidden = true
      stopTimer()
      return
    }
    pausedByHidden = false
    scheduleEnabledChange()
  }

  async function triggerNow(initial = false) {
    if (!enabledFn()) return
    await runFetch(initial)
  }

  if (options.enabled) {
    const isEnabled = computed(() => enabledFn())
    watch(isEnabled, scheduleEnabledChange)
  }

  onMounted(() => {
    if (pauseWhenHidden) {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }
    if (immediate) scheduleEnabledChange()
  })

  onUnmounted(() => {
    if (enabledDebounceTimer) clearTimeout(enabledDebounceTimer)
    stopTimer()
    if (pauseWhenHidden) {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  })

  return {
    polling: polling as Readonly<Ref<boolean>>,
    start: startTimer,
    stop: stopTimer,
    triggerNow,
  }
}
