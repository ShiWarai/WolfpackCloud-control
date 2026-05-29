import { ref } from 'vue'
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
export function useRosLogBuffer(maxLines: number) {
  const entries = ref<RosLogEntry[]>([])
  const knownIds = new Set<number>()

  function reset() {
    entries.value = []
    knownIds.clear()
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
    if (entries.value.length > maxLines) {
      const dropped = entries.value.splice(0, entries.value.length - maxLines)
      for (const entry of dropped) knownIds.delete(entry.id)
    }
    return true
  }

  return { entries, reset, merge }
}
