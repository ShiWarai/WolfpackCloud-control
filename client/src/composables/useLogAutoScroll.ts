import { nextTick, watch, type Ref } from 'vue'

export type LogAutoScrollMode = 'bottom' | 'top'

/** Скролл к новым записям только когда включена галочка `enabled`. */
export function useLogAutoScroll(
  containerRef: Ref<HTMLElement | null>,
  enabled: Ref<boolean>,
  mode: Ref<LogAutoScrollMode>,
) {
  async function scrollToEnd() {
    if (!enabled.value) return
    await nextTick()
    const el = containerRef.value
    if (!el) return
    // Двойной rAF: дождаться layout после обновления slot/v-for.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (mode.value === 'bottom') el.scrollTop = el.scrollHeight
        else el.scrollTop = 0
      })
    })
  }

  watch(enabled, (on) => {
    if (on) void scrollToEnd()
  }, { flush: 'post' })

  watch(mode, () => {
    void scrollToEnd()
  }, { flush: 'post' })

  return { scrollToEnd }
}
