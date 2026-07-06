import { describe, expect, it } from 'vitest'
import { phasorPoint, phasorToLifetime } from './phasor'

describe('phasorPoint', () => {
  it('returns the origin for empty or all-zero decays', () => {
    expect(phasorPoint([])).toEqual({ g: 0, s: 0 })
    expect(phasorPoint([0, 0, 0])).toEqual({ g: 0, s: 0 })
  })

  it('places a single-exponential decay near the universal semicircle', () => {
    const n = 32
    const tau = 6
    const counts = Array.from({ length: n }, (_, k) => Math.exp(-k / tau))
    const { g, s } = phasorPoint(counts)
    // On the semicircle g² + s² ≈ g.
    expect(Math.abs(g * g + s * s - g)).toBeLessThan(0.05)
    expect(s).toBeGreaterThan(0)
  })
})

describe('phasorToLifetime', () => {
  it('returns null for non-physical inputs', () => {
    expect(phasorToLifetime(0, 0.5, 1e8)).toBeNull()
    expect(phasorToLifetime(0.5, 0.5, 0)).toBeNull()
  })

  it('is positive for a valid phasor', () => {
    const tau = phasorToLifetime(0.5, 0.4, 2 * Math.PI * 40e6)
    expect(tau).not.toBeNull()
    expect(tau as number).toBeGreaterThan(0)
  })
})
