import { nextTick, watch, type Ref } from 'vue'

export type LogAutoScrollMode = 'bottom' | 'top'

const SCROLL_EDGE_PX = 2
const MAX_SCROLL_ATTEMPTS = 24

export function isAtScrollEnd(el: HTMLElement, mode: LogAutoScrollMode): boolean {
  if (mode === 'bottom') {
    return el.scrollTop + el.clientHeight >= el.scrollHeight - SCROLL_EDGE_PX
  }
  return el.scrollTop <= SCROLL_EDGE_PX
}

function applyScrollEnd(el: HTMLElement, mode: LogAutoScrollMode) {
  if (mode === 'bottom') {
    el.scrollTop = el.scrollHeight
  } else {
    el.scrollTop = 0
  }
}

function applyScrollTop(el: HTMLElement, scrollTop: number) {
  const maxTop = Math.max(0, el.scrollHeight - el.clientHeight)
  el.scrollTop = Math.min(Math.max(0, scrollTop), maxTop)
}

async function restoreScrollTop(
  containerRef: Ref<HTMLElement | null>,
  scrollTop: number,
): Promise<void> {
  await nextTick()
  let attempts = 0

  const run = () => {
    const el = containerRef.value
    if (!el) return
    applyScrollTop(el, scrollTop)
    if (Math.abs(el.scrollTop - scrollTop) > 1 && attempts < MAX_SCROLL_ATTEMPTS) {
      attempts += 1
      requestAnimationFrame(run)
    }
  }

  requestAnimationFrame(run)
}

/** Скролл к новым записям только когда включена галочка `enabled`. */
export function useLogAutoScroll(
  containerRef: Ref<HTMLElement | null>,
  enabled: Ref<boolean>,
  mode: Ref<LogAutoScrollMode>,
) {
  let pendingScrollTop: number | null = null

  function captureIfDisabled() {
    if (enabled.value) return
    const el = containerRef.value
    if (!el) return
    pendingScrollTop = el.scrollTop
  }

  async function scrollToEnd() {
    if (!enabled.value) return
    pendingScrollTop = null
    await nextTick()
    const el = containerRef.value
    if (!el) return

    let attempts = 0
    const run = () => {
      if (!enabled.value) return
      const current = containerRef.value
      if (!current) return

      applyScrollEnd(current, mode.value)
      if (!isAtScrollEnd(current, mode.value) && attempts < MAX_SCROLL_ATTEMPTS) {
        attempts += 1
        requestAnimationFrame(run)
      }
    }

    requestAnimationFrame(run)
  }

  async function onContentUpdated() {
    if (enabled.value) {
      await scrollToEnd()
      return
    }
    if (pendingScrollTop === null) return
    const top = pendingScrollTop
    pendingScrollTop = null
    await restoreScrollTop(containerRef, top)
  }

  watch(enabled, (on) => {
    if (on) void scrollToEnd()
  }, { flush: 'post' })

  watch(mode, () => {
    void scrollToEnd()
  }, { flush: 'post' })

  return { scrollToEnd, captureIfDisabled, onContentUpdated, isAtScrollEnd }
}
