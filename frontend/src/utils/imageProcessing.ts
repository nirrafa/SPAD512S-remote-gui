// Pure image/ROI helpers operating on a decoded preview grid (row-major uint8,
// `width × height`). ROIs are expressed in grid coordinates so callers map
// display pixels → grid before calling; keeping the math grid-space makes it
// unit-testable and independent of canvas zoom/downsampling.

export type Point = [number, number]

export interface RectangleRoi {
  id: string
  type: 'rectangle'
  label: string
  x: number
  y: number
  width: number
  height: number
}

export interface FreehandRoi {
  id: string
  type: 'freehand'
  label: string
  points: Point[]
}

export type Roi = RectangleRoi | FreehandRoi

export interface RoiStats {
  count: number
  sum: number
  mean: number
  area: number
  min: number
  max: number
}

export interface Histogram {
  counts: number[]
  binEdges: number[]
  maxCount: number
}

export interface IntensityRange {
  min: number
  max: number
}

const EMPTY_STATS: RoiStats = { count: 0, sum: 0, mean: 0, area: 0, min: 0, max: 0 }

export function pointInPolygon(x: number, y: number, points: Point[]): boolean {
  let inside = false
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i] ?? [0, 0]
    const [xj, yj] = points[j] ?? [0, 0]
    const intersects = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
    if (intersects) inside = !inside
  }
  return inside
}

function accumulate(
  values: Uint8Array,
  width: number,
  height: number,
  contains: (x: number, y: number) => boolean,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
): RoiStats {
  let count = 0
  let sum = 0
  let min = Infinity
  let max = -Infinity
  for (let y = Math.max(0, y0); y < Math.min(height, y1); y++) {
    for (let x = Math.max(0, x0); x < Math.min(width, x1); x++) {
      if (!contains(x, y)) continue
      const v = values[y * width + x] ?? 0
      count += 1
      sum += v
      if (v < min) min = v
      if (v > max) max = v
    }
  }
  if (count === 0) return { ...EMPTY_STATS }
  return { count, sum, mean: sum / count, area: count, min, max }
}

export function roiStats(
  values: Uint8Array,
  width: number,
  height: number,
  roi: Roi,
): RoiStats {
  if (roi.type === 'rectangle') {
    const x0 = Math.floor(Math.min(roi.x, roi.x + roi.width))
    const x1 = Math.ceil(Math.max(roi.x, roi.x + roi.width))
    const y0 = Math.floor(Math.min(roi.y, roi.y + roi.height))
    const y1 = Math.ceil(Math.max(roi.y, roi.y + roi.height))
    return accumulate(values, width, height, () => true, x0, y0, x1, y1)
  }
  const xs = roi.points.map((p) => p[0])
  const ys = roi.points.map((p) => p[1])
  if (xs.length === 0) return { ...EMPTY_STATS }
  const x0 = Math.floor(Math.min(...xs))
  const x1 = Math.ceil(Math.max(...xs))
  const y0 = Math.floor(Math.min(...ys))
  const y1 = Math.ceil(Math.max(...ys))
  return accumulate(
    values,
    width,
    height,
    (x, y) => pointInPolygon(x + 0.5, y + 0.5, roi.points),
    x0,
    y0,
    x1,
    y1,
  )
}

export function histogram(values: Uint8Array, bins = 64): Histogram {
  const counts = new Array<number>(bins).fill(0)
  const scale = bins / 256
  for (let i = 0; i < values.length; i++) {
    const v = values[i] ?? 0
    const bin = Math.min(bins - 1, Math.floor(v * scale))
    counts[bin] = (counts[bin] ?? 0) + 1
  }
  const binEdges = Array.from({ length: bins + 1 }, (_, i) => Math.round((i / bins) * 256))
  const maxCount = counts.reduce((m, c) => Math.max(m, c), 0)
  return { counts, binEdges, maxCount }
}

/** Percentile-based contrast stretch over the grid values (0–255). */
export function autoStretchRange(values: Uint8Array, loPct = 1, hiPct = 99): IntensityRange {
  if (values.length === 0) return { min: 0, max: 255 }
  const hist = new Array<number>(256).fill(0)
  for (let i = 0; i < values.length; i++) {
    const idx = values[i] ?? 0
    hist[idx] = (hist[idx] ?? 0) + 1
  }
  const total = values.length
  const loTarget = (loPct / 100) * total
  const hiTarget = (hiPct / 100) * total
  let cum = 0
  let min = 0
  let max = 255
  for (let v = 0; v < 256; v++) {
    cum += hist[v] ?? 0
    if (cum >= loTarget) {
      min = v
      break
    }
  }
  cum = 0
  for (let v = 255; v >= 0; v--) {
    cum += hist[v] ?? 0
    if (cum >= total - hiTarget) {
      max = v
      break
    }
  }
  if (max <= min) max = Math.min(255, min + 1)
  return { min, max }
}

/** Linearly remap grid values into [0,255] over [range.min, range.max]. */
export function stretchValues(values: Uint8Array, range: IntensityRange): Uint8Array {
  const span = Math.max(1, range.max - range.min)
  const out = new Uint8Array(values.length)
  for (let i = 0; i < values.length; i++) {
    const v = ((values[i] ?? 0) - range.min) / span
    out[i] = Math.max(0, Math.min(255, Math.round(v * 255)))
  }
  return out
}

/** Scale an ROI from one coordinate space to another (e.g. 512-display →
 * preview grid) so stats can run against the decoded preview. */
export function scaleRoi(roi: Roi, sx: number, sy: number): Roi {
  if (roi.type === 'rectangle') {
    return { ...roi, x: roi.x * sx, y: roi.y * sy, width: roi.width * sx, height: roi.height * sy }
  }
  return { ...roi, points: roi.points.map(([x, y]) => [x * sx, y * sy] as Point) }
}

/** Per-step ROI mean across a gated preview stack → decay counts. */
export function decayFromStack(
  stack: (Uint8Array | null)[],
  width: number,
  height: number,
  roi: Roi,
): number[] {
  return stack.map((frame) => (frame ? roiStats(frame, width, height, roi).mean : 0))
}
