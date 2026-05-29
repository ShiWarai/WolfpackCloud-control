import { computed, ref, type Ref } from 'vue'

import type { WorkerNode } from '@/api/cluster'

const DRAG_START_THRESHOLD_PX = 10

export interface UsePodDragDropOptions {
  workerNodes: Ref<WorkerNode[]>
  isDeploymentBusy: (deploymentName: string | undefined) => boolean
  onDrop: (deploymentName: string, targetNode: WorkerNode) => void | Promise<void>
}

export function usePodDragDrop(options: UsePodDragDropOptions) {
  const dragged = ref<{ deploymentName: string; podName: string } | null>(null)
  const dragState = ref<{
    deploymentName: string
    podName: string
    sourceNodeName: string | null
    pointerId: number
    startX: number
    startY: number
  } | null>(null)
  const dragActive = ref(false)
  const dragGhostPos = ref({ x: 0, y: 0 })
  const dragOverNode = ref<string | null>(null)

  const dragGhostLabel = computed(() => dragState.value?.deploymentName ?? '')
  const showDragGhost = computed(() => dragActive.value && !!dragState.value)

  function cleanupDragListeners() {
    window.removeEventListener('pointermove', onWindowPointerMove)
    window.removeEventListener('pointerup', onWindowPointerUp)
    window.removeEventListener('pointercancel', onWindowPointerUp)
  }

  function resetDragState() {
    dragState.value = null
    dragActive.value = false
    dragOverNode.value = null
    dragged.value = null
  }

  function onWindowPointerMove(ev: PointerEvent) {
    if (!dragState.value || ev.pointerId !== dragState.value.pointerId) return

    if (!dragActive.value) {
      const dx = ev.clientX - dragState.value.startX
      const dy = ev.clientY - dragState.value.startY
      if (Math.hypot(dx, dy) < DRAG_START_THRESHOLD_PX) return
      dragActive.value = true
      dragged.value = {
        deploymentName: dragState.value.deploymentName,
        podName: dragState.value.podName,
      }
    }

    ev.preventDefault()
    dragGhostPos.value = { x: ev.clientX, y: ev.clientY }

    const under = document.elementFromPoint(ev.clientX, ev.clientY)
    const zone = under?.closest('[data-drop-node]') as HTMLElement | null
    const nodeName = zone?.dataset.dropNode
    if (!nodeName) {
      dragOverNode.value = null
      return
    }
    const node = options.workerNodes.value.find((n) => n.name === nodeName)
    const sourceNode = dragState.value.sourceNodeName
    if (!node?.ready || (sourceNode && nodeName === sourceNode)) {
      dragOverNode.value = null
      return
    }
    dragOverNode.value = nodeName
  }

  async function onWindowPointerUp(ev: PointerEvent) {
    if (!dragState.value || ev.pointerId !== dragState.value.pointerId) return

    cleanupDragListeners()

    const dep = dragState.value.deploymentName
    const sourceNodeName = dragState.value.sourceNodeName
    const targetNodeName = dragOverNode.value
    const wasDragging = dragActive.value

    resetDragState()

    if (!wasDragging || !targetNodeName) return
    if (sourceNodeName && targetNodeName === sourceNodeName) return
    const node = options.workerNodes.value.find((n) => n.name === targetNodeName)
    if (node) await options.onDrop(dep, node)
  }

  function onPodPointerDown(
    dep: string | undefined,
    pod: string,
    ev: PointerEvent,
    sourceNodeName?: string | null,
  ) {
    if (!dep || options.isDeploymentBusy(dep)) return
    if (ev.pointerType === 'mouse' && ev.button !== 0) return

    resetDragState()
    dragState.value = {
      deploymentName: dep,
      podName: pod,
      sourceNodeName: sourceNodeName ?? null,
      pointerId: ev.pointerId,
      startX: ev.clientX,
      startY: ev.clientY,
    }

    window.addEventListener('pointermove', onWindowPointerMove, { passive: false })
    window.addEventListener('pointerup', onWindowPointerUp)
    window.addEventListener('pointercancel', onWindowPointerUp)
  }

  function dispose() {
    cleanupDragListeners()
    resetDragState()
  }

  return {
    dragged,
    dragActive,
    dragGhostPos,
    dragOverNode,
    dragGhostLabel,
    showDragGhost,
    onPodPointerDown,
    dispose,
  }
}
