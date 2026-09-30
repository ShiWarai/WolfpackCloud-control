import { ref, type Ref } from 'vue'
import type { RosLogEntry } from '@/api/logs'

function sortLogEntries(entries: RosLogEntry[]): RosLogEntry[] {
  return [...entries].sort((a, b) => {
    const ta = new Date(a.recorded_at).getTime()
    const tb = new Date(b.recorded_at).getTime()
    if (ta !== tb) return ta - tb
    return a.id - b.id
  })
}

/** Накопление ROS-логов с дедупом по id и обрезкой хвоста. */
export function useRosLogBuffer(
  maxLines: number,
  /** true — не удалять старые строки сверху (режим чтения без автоскролла). */
  freezeTrim: Ref<boolean> = ref(false),
) {
  const entries = ref<RosLogEntry[]>([])
  /** +1 при любом изменении списка. */
  const scrollGeneration = ref(0)
  const knownIds = new Set<number>()

  function trimToMax() {
    if (entries.value.length <= maxLines) return
    const dropped = entries.value.splice(0, entries.value.length - maxLines)
    for (const entry of dropped) knownIds.delete(entry.id)
  }

  function reset() {
    entries.value = []
    knownIds.clear()
    scrollGeneration.value = 0
  }

  /** @returns true если добавлены новые строки */
  function merge(incoming: RosLogEntry[]): boolean {
    const added: RosLogEntry[] = []
    for (const entry of sortLogEntries(incoming)) {
      if (knownIds.has(entry.id)) continue
      knownIds.add(entry.id)
      added.push(entry)
    }
    if (!added.length) return false

    entries.value = [...entries.value, ...added]
    if (!freezeTrim.value) {
      trimToMax()
    }
    scrollGeneration.value += 1
    return true
  }

  /** После выключения freeze — обрезать до лимита (напр. при включении автоскролла). */
  function trimNow() {
    const before = entries.value.length
    trimToMax()
    if (entries.value.length !== before) {
      scrollGeneration.value += 1
    }
  }

  return { entries, reset, merge, trimNow, scrollGeneration }
}
