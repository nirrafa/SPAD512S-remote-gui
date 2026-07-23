// Pending-queue builder state, shared across tabs (each mode page's
// "Add to queue" writes here; the Queue tab reads it). localStorage-backed so
// it survives tab switches and reloads; the bridge only sees the list when
// the user presses Run.
import type { QueueItemSpec } from '../api/types'

const KEY = 'spad-queue-items'

export function loadQueueItems(): QueueItemSpec[] {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(parsed) ? (parsed as QueueItemSpec[]) : []
  } catch {
    return []
  }
}

function save(items: QueueItemSpec[]): void {
  localStorage.setItem(KEY, JSON.stringify(items))
}

export function addQueueItem(mode: 'intensity' | 'gated', params: Record<string, unknown>): number {
  const items = loadQueueItems()
  items.push({ mode, params, repeat: 1 })
  save(items)
  return items.length
}

export function updateQueueRepeat(index: number, repeat: number): QueueItemSpec[] {
  const items = loadQueueItems()
  if (items[index]) items[index].repeat = Math.max(1, Math.min(100, Math.round(repeat)))
  save(items)
  return items
}

export function removeQueueItem(index: number): QueueItemSpec[] {
  const items = loadQueueItems()
  items.splice(index, 1)
  save(items)
  return items
}

export function clearQueueItems(): QueueItemSpec[] {
  save([])
  return []
}
