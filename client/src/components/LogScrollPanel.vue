<script setup lang="ts">
import { ref, toRef, watch } from 'vue'
import { useLogAutoScroll, type LogAutoScrollMode } from '@/composables/useLogAutoScroll'

const props = withDefaults(
  defineProps<{
    title: string
    hint?: string
    loading?: boolean
    empty?: boolean
    emptyText?: string
    alertText?: string | null
    /** Меняется при обновлении данных — триггер автоскролла (напр. items.length). */
    scrollTrigger?: number
    scrollMode?: LogAutoScrollMode
    /** monospaced log lines vs произвольный контент (таблица). */
    variant?: 'log' | 'plain'
  }>(),
  {
    loading: false,
    empty: false,
    emptyText: 'Нет записей.',
    alertText: null,
    scrollTrigger: 0,
    scrollMode: 'bottom',
    variant: 'log',
  },
)

const autoScroll = ref(true)
const containerRef = ref<HTMLElement | null>(null)
const { scrollToEnd } = useLogAutoScroll(containerRef, autoScroll, toRef(props, 'scrollMode'))

watch(
  () => props.scrollTrigger,
  () => {
    void scrollToEnd()
  },
  { flush: 'post' },
)

watch(
  () => props.loading,
  (loading, wasLoading) => {
    if (wasLoading && !loading) void scrollToEnd()
  },
  { flush: 'post' },
)
</script>

<template>
  <div class="term-card log-scroll-panel" :class="{ 'log-scroll-panel--plain': variant === 'plain' }">
    <div class="log-scroll-panel__toolbar">
      <h2 class="log-scroll-panel__title">
        {{ title }}
        <span v-if="hint" class="log-scroll-panel__hint" :title="hint">?</span>
      </h2>
      <div class="log-scroll-panel__actions">
        <label class="log-scroll-panel__auto-scroll">
          <input v-model="autoScroll" type="checkbox" />
          <span>Автоскролл</span>
        </label>
        <slot name="toolbar" />
      </div>
    </div>

    <div v-if="alertText" class="term-alert term-alert-error log-scroll-panel__alert">
      {{ alertText }}
    </div>

    <div
      ref="containerRef"
      class="log-scroll-panel__viewport"
      :class="{ 'log-scroll-panel__viewport--plain': variant === 'plain' }"
    >
      <div v-if="loading && empty" class="term-text-dim log-scroll-panel__placeholder">
        Загрузка...
      </div>
      <div v-else-if="empty" class="term-text-dim log-scroll-panel__placeholder">
        {{ emptyText }}
      </div>
      <slot v-else />
    </div>
  </div>
</template>

<style scoped>
.log-scroll-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.log-scroll-panel__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.log-scroll-panel__title {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-size: inherit;
  font-weight: inherit;
}

.log-scroll-panel__hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 0.95rem;
  height: 0.95rem;
  border: 1px solid var(--border);
  border-radius: 50%;
  font-size: 0.625rem;
  line-height: 1;
  color: var(--text-dim);
  cursor: help;
  flex-shrink: 0;
}

.log-scroll-panel__hint:hover {
  color: var(--accent, #fb923c);
  border-color: rgba(251, 146, 60, 0.55);
}

.log-scroll-panel__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.log-scroll-panel__auto-scroll {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--fs-xs);
  cursor: pointer;
  user-select: none;
}

.log-scroll-panel__auto-scroll input {
  margin: 0;
  accent-color: var(--accent, #fb923c);
}

.log-scroll-panel__alert {
  margin-bottom: 0.75rem;
  font-size: var(--fs-xs);
}

.log-scroll-panel__viewport {
  height: min(32rem, calc(100vh - 12rem));
  min-height: 14rem;
  overflow: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 0.75rem 1rem;
  font-size: var(--fs-xs);
  line-height: 1.45;
  color: var(--text-dim);
}

.log-scroll-panel--plain .log-scroll-panel__viewport--plain {
  padding: 0;
  height: min(32rem, calc(100vh - 12rem));
  min-height: 14rem;
}

.log-scroll-panel__placeholder {
  font-size: var(--fs-xs);
}

:deep(.log-scroll-panel__line) {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

:deep(.log-scroll-panel__line + .log-scroll-panel__line) {
  margin-top: 0.15rem;
}
</style>
