// First-harmonic phasor of a decay (counts sampled over N gate steps).
// g = Σ cₖ·cos(ωk) / Σ cₖ, s = Σ cₖ·sin(ωk) / Σ cₖ, ω = 2π/N.
// A single-exponential decay lands on the universal semicircle g²+s² = g.

export interface PhasorPoint {
  g: number
  s: number
}

export function phasorPoint(counts: number[]): PhasorPoint {
  const n = counts.length
  if (n === 0) return { g: 0, s: 0 }
  const omega = (2 * Math.PI) / n
  let re = 0
  let im = 0
  let total = 0
  for (let k = 0; k < n; k++) {
    const c = counts[k] ?? 0
    re += c * Math.cos(omega * k)
    im += c * Math.sin(omega * k)
    total += c
  }
  if (total === 0) return { g: 0, s: 0 }
  return { g: re / total, s: im / total }
}

/** Convert a phasor point to a modulation lifetime (ns) given the laser
 * angular frequency ω (rad/s). Returns null when off the physical range. */
export function phasorToLifetime(g: number, s: number, omegaRadPerS: number): number | null {
  if (omegaRadPerS <= 0 || g === 0) return null
  const tauSeconds = s / (g * omegaRadPerS)
  if (!Number.isFinite(tauSeconds) || tauSeconds < 0) return null
  return tauSeconds * 1e9
}
