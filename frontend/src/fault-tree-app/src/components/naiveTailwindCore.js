export const DEFAULT_NODE_SAFE_PADDING = 8

export function createIncrementId(prefix, startAt = 1) {
  let next = Math.max(1, Number(startAt) || 1)
  return () => `${prefix}${next++}`
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

export function rectFromNodePosition(x, y, width, height, padding = DEFAULT_NODE_SAFE_PADDING) {
  return {
    left: x - padding,
    top: y - padding,
    right: x + width + padding,
    bottom: y + height + padding,
    width: width + padding * 2,
    height: height + padding * 2
  }
}

export function rectIntersectionArea(a, b) {
  const ix = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
  const iy = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top))
  return ix * iy
}

export function computeMinimumTranslationVector(a, b) {
  const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left)
  const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
  if (overlapX <= 0 || overlapY <= 0) return { x: 0, y: 0, magnitude: 0 }

  const aCx = (a.left + a.right) / 2
  const aCy = (a.top + a.bottom) / 2
  const bCx = (b.left + b.right) / 2
  const bCy = (b.top + b.bottom) / 2

  if (overlapX < overlapY) {
    const dir = aCx < bCx ? -1 : 1
    const dx = overlapX * dir
    return { x: dx, y: 0, magnitude: Math.abs(dx) }
  }
  const dir = aCy < bCy ? -1 : 1
  const dy = overlapY * dir
  return { x: 0, y: dy, magnitude: Math.abs(dy) }
}

export function snapToGrid(value, step) {
  const s = Number(step) || 0
  if (s <= 0) return value
  return Math.round(value / s) * s
}

export function resolveDragCollision({
  movingId,
  proposed,
  nodes,
  nodeWidth,
  nodeHeight,
  getNodeSize,
  safePadding = DEFAULT_NODE_SAFE_PADDING,
  gridStep = 18,
  bounds,
  maxIterations = 24
}) {
  let x = proposed.x
  let y = proposed.y

  const minX = bounds?.minX ?? 0
  const minY = bounds?.minY ?? 0
  const maxX = bounds?.maxX ?? Infinity
  const maxY = bounds?.maxY ?? Infinity

  x = clamp(x, minX, maxX)
  y = clamp(y, minY, maxY)

  const resolveSize = (n) => {
    if (typeof getNodeSize === 'function') {
      const res = getNodeSize(n)
      const w = Number(res?.width)
      const h = Number(res?.height)
      if (Number.isFinite(w) && w > 0 && Number.isFinite(h) && h > 0) return { width: w, height: h }
    }
    return { width: nodeWidth, height: nodeHeight }
  }

  const movingNode = (Array.isArray(nodes) ? nodes : []).find((n) => n?.id === movingId) ?? null
  const movingSize = resolveSize(movingNode)
  const baseArea = Math.max(1, movingSize.width * movingSize.height)

  for (let iter = 0; iter < maxIterations; iter++) {
    const movingRect = rectFromNodePosition(x, y, movingSize.width, movingSize.height, safePadding)

    let bestMtv = null
    let bestArea = 0
    let forceX = 0
    let forceY = 0
    let overlaps = 0

    for (const n of nodes) {
      if (!n || n.id === movingId) continue
      const otherSize = resolveSize(n)
      const otherRect = rectFromNodePosition(n.x, n.y, otherSize.width, otherSize.height, safePadding)
      const area = rectIntersectionArea(movingRect, otherRect)
      if (area <= 0) continue
      overlaps++
      const mtv = computeMinimumTranslationVector(movingRect, otherRect)
      if (mtv.magnitude > 0) {
        const w = Math.min(2.2, 0.6 + area / baseArea)
        forceX += mtv.x * w
        forceY += mtv.y * w
        if (!bestMtv || mtv.magnitude < bestMtv.magnitude) {
          bestMtv = mtv
          bestArea = area
        }
      }
    }

    if (!overlaps) break

    if (bestMtv) {
      const fx = forceX / overlaps
      const fy = forceY / overlaps
      const k = 0.35 + Math.min(0.45, bestArea / baseArea)
      x += bestMtv.x + fx * k
      y += bestMtv.y + fy * k
    } else {
      x += (Math.random() - 0.5) * 2
      y += (Math.random() - 0.5) * 2
    }

    x = clamp(snapToGrid(x, gridStep), minX, maxX)
    y = clamp(snapToGrid(y, gridStep), minY, maxY)
  }

  return { x, y }
}

export function hasEdgeBetweenNodes(edges, fromId, toId) {
  for (const e of edges) {
    if (!e) continue
    if ((e.source === fromId && e.target === toId) || (e.source === toId && e.target === fromId)) return true
  }
  return false
}

export function canAddEdge(edges, fromId, toId, { allowMultipleEdges = false, ignoreEdgeId = '' } = {}) {
  if (allowMultipleEdges) return true
  for (const e of edges) {
    if (!e || e.id === ignoreEdgeId) continue
    if ((e.source === fromId && e.target === toId) || (e.source === toId && e.target === fromId)) return false
  }
  return true
}

export function defaultClone(value) {
  if (typeof structuredClone === 'function') return structuredClone(value)
  return JSON.parse(JSON.stringify(value))
}

export class HistoryManager {
  constructor({ capacity = 50, clone = defaultClone } = {}) {
    this.capacity = Math.max(1, Number(capacity) || 50)
    this.clone = clone
    this.past = []
    this.future = []
    this.version = 0
  }

  canUndo() {
    return this.past.length > 0
  }

  canRedo() {
    return this.future.length > 0
  }

  clear() {
    this.past = []
    this.future = []
    this.version++
  }

  execute(command) {
    if (!command || typeof command.do !== 'function' || typeof command.undo !== 'function') return
    command.do()
    this.past.push(command)
    if (this.past.length > this.capacity) this.past.splice(0, this.past.length - this.capacity)
    this.future = []
    this.version++
  }

  undo() {
    const cmd = this.past.pop()
    if (!cmd) return
    cmd.undo()
    this.future.push(cmd)
    this.version++
  }

  redo() {
    const cmd = this.future.pop()
    if (!cmd) return
    cmd.do()
    this.past.push(cmd)
    if (this.past.length > this.capacity) this.past.splice(0, this.past.length - this.capacity)
    this.version++
  }
}

export function normalizeEdgeStyle(style, { defaultColor = '#22d3ee', defaultWidth = 4 } = {}) {
  const color = style?.color ?? defaultColor
  const width = Number(style?.width)
  return { color, width: Number.isFinite(width) && width > 0 ? width : defaultWidth }
}

export function deleteEdge(edges, edgeId) {
  return (Array.isArray(edges) ? edges : []).filter((e) => e?.id !== edgeId)
}

export function deleteNodeAndRelatedEdges(nodes, edges, nodeId) {
  const nextNodes = (Array.isArray(nodes) ? nodes : []).filter((n) => n?.id !== nodeId)
  const nextEdges = (Array.isArray(edges) ? edges : []).filter((e) => e?.source !== nodeId && e?.target !== nodeId)
  return { nodes: nextNodes, edges: nextEdges }
}

export function pointsToPolylinePath(points) {
  if (!Array.isArray(points) || points.length === 0) return ''
  const first = points[0]
  let d = `M ${first.x} ${first.y}`
  for (let i = 1; i < points.length; i++) {
    const p = points[i]
    const prev = points[i - 1]
    const diagonal = prev && p && prev.x !== p.x && prev.y !== p.y
    if (diagonal) d += ` L ${p.x} ${prev.y}`
    d += ` L ${p.x} ${p.y}`
  }
  return d
}

