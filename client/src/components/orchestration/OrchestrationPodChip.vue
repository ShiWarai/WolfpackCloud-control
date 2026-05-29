<script setup lang="ts">
import type { ClusterPod } from '@/api/cluster'

defineProps<{
  pod: ClusterPod
  busy: boolean
  dragActive: boolean
  draggedDeployment: string | null | undefined
  showNodeName?: boolean
}>()

const emit = defineEmits<{
  pointerdown: [ev: PointerEvent]
  stop: []
}>()
</script>

<template>
  <div
    class="orchestration-pod-chip term-btn"
    :class="{ 'orchestration-pod-chip--busy': busy }"
  >
    <span
      class="orchestration-pod-chip__drag"
      :class="{
        'orchestration-pod-chip__drag--active': dragActive && draggedDeployment === pod.deploymentName,
        'orchestration-pod-chip__drag--busy': busy,
      }"
      :title="showNodeName ? `${pod.deploymentName || pod.name} @ ${pod.nodeName || '?'}` : (pod.deploymentName || pod.name)"
      @pointerdown="emit('pointerdown', $event)"
    >
      <span v-if="busy" class="orchestration-pod-chip__spinner" aria-hidden="true" />
      {{ pod.deploymentName || pod.name }}
      <span v-if="showNodeName" class="term-text-dim"> @{{ pod.nodeName }}</span>
    </span>
    <button
      v-if="pod.deploymentName"
      type="button"
      class="orchestration-pod-chip__close"
      :disabled="busy"
      title="Остановить под (deployment → 0 реплик)"
      @click.stop.prevent="emit('stop')"
    >
      ×
    </button>
  </div>
</template>

<style scoped>
.orchestration-pod-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  font-size: var(--fs-2xs);
  padding: 0.2rem 0.35rem 0.2rem 0.45rem;
}

.orchestration-pod-chip--busy {
  border-color: rgba(251, 146, 60, 0.45);
  box-shadow: 0 0 0 1px rgba(251, 146, 60, 0.2);
}

.orchestration-pod-chip__drag {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  cursor: grab;
  flex: 1;
  min-width: 0;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}

.orchestration-pod-chip__drag--active {
  opacity: 0.45;
}

.orchestration-pod-chip__drag--busy {
  cursor: wait;
  pointer-events: none;
}

.orchestration-pod-chip__spinner {
  display: inline-block;
  width: 0.85rem;
  height: 0.85rem;
  border: 2px solid rgba(251, 146, 60, 0.25);
  border-top-color: var(--accent, #fb923c);
  border-radius: 50%;
  animation: orchestration-pod-spin 0.75s linear infinite;
  flex-shrink: 0;
}

@keyframes orchestration-pod-spin {
  to {
    transform: rotate(360deg);
  }
}

.orchestration-pod-chip__close {
  flex-shrink: 0;
  width: 1.35rem;
  height: 1.35rem;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted, #888);
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.orchestration-pod-chip__close:hover:not(:disabled) {
  color: var(--accent, #fb923c);
  background: rgba(251, 146, 60, 0.12);
}

.orchestration-pod-chip__close:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
