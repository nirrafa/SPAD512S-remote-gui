import { describe, expect, it } from 'vitest'
import {
  autoStretchRange,
  decayFromStack,
  histogram,
  pointInPolygon,
  roiStats,
  stretchValues,
  type FreehandRoi,
  type RectangleRoi,
} from './imageProcessing'

function grid(width: number, height: number, fill: (x: number, y: number) => number): Uint8Array {
  const out = new Uint8Array(width * height)
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) out[y * width + x] = fill(x, y)
  return out
}

describe('roiStats', () => {
  it('computes rectangle mean/sum/area over the box', () => {
    const values = grid(4, 4, () => 10)
    const roi: RectangleRoi = { id: 'r', type: 'rectangle', label: 'A', x: 1, y: 1, width: 2, height: 2 }
    const stats = roiStats(values, 4, 4, roi)
    expect(stats.area).toBe(4)
    expect(stats.sum).toBe(40)
    expect(stats.mean).toBe(10)
  })

  it('clips a rectangle to the grid bounds', () => {
    const values = grid(4, 4, () => 5)
    const roi: RectangleRoi = { id: 'r', type: 'rectangle', label: 'A', x: 3, y: 3, width: 5, height: 5 }
    const stats = roiStats(values, 4, 4, roi)
    expect(stats.area).toBe(1)
  })

  it('accumulates only pixels inside a freehand polygon', () => {
    const values = grid(10, 10, () => 2)
    const roi: FreehandRoi = {
      id: 'f',
      type: 'freehand',
      label: 'B',
      points: [
        [0, 0],
        [6, 0],
        [6, 6],
        [0, 6],
      ],
    }
    const stats = roiStats(values, 10, 10, roi)
    expect(stats.area).toBe(36)
    expect(stats.mean).toBe(2)
  })
})

describe('pointInPolygon', () => {
  const square: [number, number][] = [
    [0, 0],
    [4, 0],
    [4, 4],
    [0, 4],
  ]
  it('detects inside and outside points', () => {
    expect(pointInPolygon(2, 2, square)).toBe(true)
    expect(pointInPolygon(5, 5, square)).toBe(false)
  })
})

describe('histogram', () => {
  it('bins values and reports the tallest bin', () => {
    const values = new Uint8Array([0, 0, 255, 128])
    const h = histogram(values, 4)
    expect(h.counts.reduce((a, b) => a + b, 0)).toBe(4)
    expect(h.counts[0]).toBe(2)
    expect(h.maxCount).toBe(2)
    expect(h.binEdges).toHaveLength(5)
  })
})

describe('autoStretchRange / stretchValues', () => {
  it('derives a clipped percentile range and remaps it to full scale', () => {
    const values = grid(10, 10, (x) => 100 + x) // 100..109, 10 px each
    const range = autoStretchRange(values, 20, 80)
    expect(range.min).toBeGreaterThanOrEqual(100)
    expect(range.max).toBeLessThanOrEqual(109)
    expect(range.max).toBeGreaterThan(range.min)
    // Values at/above the range max saturate to full scale after stretching.
    const stretched = stretchValues(values, range)
    expect(Math.max(...stretched)).toBe(255)
  })

  it('never returns an inverted range', () => {
    const flat = new Uint8Array(16).fill(42)
    const range = autoStretchRange(flat)
    expect(range.max).toBeGreaterThan(range.min)
  })
})

describe('decayFromStack', () => {
  it('returns per-step ROI means and zero for missing frames', () => {
    const roi: RectangleRoi = { id: 'r', type: 'rectangle', label: 'A', x: 0, y: 0, width: 2, height: 2 }
    const stack = [grid(2, 2, () => 4), null, grid(2, 2, () => 8)]
    const decay = decayFromStack(stack, 2, 2, roi)
    expect(decay).toEqual([4, 0, 8])
  })
})
