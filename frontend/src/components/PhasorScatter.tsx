import type { PhasorData } from '../api/types'

interface Props {
  phasor: PhasorData | null
  size?: number
}

// Basic phasor scatter (g on x, s on y) over the universal semicircle.
// Full interactive visualization is Phase 11.
export function PhasorScatter({ phasor, size = 260 }: Props) {
  const pad = 20
  const w = size + pad * 2
  const h = size / 2 + pad * 2
  const x = (g: number) => pad + g * size
  const y = (s: number) => pad + (1 - s * 2) * (size / 2)

  if (!phasor || phasor.g.length === 0) {
    return <p className="muted">Phasor appears here after a FLIM acquisition.</p>
  }

  return (
    <svg className="phasor" width={w} height={h} role="img" aria-label="Phasor plot">
      <path
        d={`M ${x(0)} ${y(0)} A ${size / 2} ${size / 2} 0 0 1 ${x(1)} ${y(0)}`}
        fill="none"
        stroke="#555"
      />
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(0)} stroke="#555" />
      {phasor.g.map((g, i) => (
        <circle key={i} cx={x(g)} cy={y(phasor.s[i] ?? 0)} r={1.3} fill="#4caf50" opacity={0.5} />
      ))}
    </svg>
  )
}
