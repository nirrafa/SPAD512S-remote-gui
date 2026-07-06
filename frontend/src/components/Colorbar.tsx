import { useMemo } from 'react'
import { applyColormap, type ColormapName } from '../utils/colormap'

interface Props {
  colormap: ColormapName
  min: number
  max: number
  unit?: string
  label?: string
}

const W = 220
const H = 44

export function Colorbar({ colormap, min, max, unit = 'ns', label = 'Lifetime' }: Props) {
  const gradientId = `cb-${colormap}`
  const stops = useMemo(() => {
    const steps = 16
    const ramp = new Uint8Array(steps)
    for (let i = 0; i < steps; i++) ramp[i] = Math.round((i / (steps - 1)) * 255)
    const rgba = applyColormap(ramp, colormap)
    return Array.from({ length: steps }, (_, i) => ({
      offset: `${(i / (steps - 1)) * 100}%`,
      color: `rgb(${rgba[i * 4]},${rgba[i * 4 + 1]},${rgba[i * 4 + 2]})`,
    }))
  }, [colormap])

  return (
    <svg className="colorbar" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label} scale`}>
      <defs>
        <linearGradient id={gradientId} x1="0" x2="1" y1="0" y2="0">
          {stops.map((s) => (
            <stop key={s.offset} offset={s.offset} stopColor={s.color} />
          ))}
        </linearGradient>
      </defs>
      <rect x={8} y={6} width={W - 16} height={14} fill={`url(#${gradientId})`} stroke="#555" />
      <text x={8} y={34} fontSize={11}>
        {min.toFixed(1)} {unit}
      </text>
      <text x={W - 8} y={34} fontSize={11} textAnchor="end">
        {max.toFixed(1)} {unit}
      </text>
      <text x={W / 2} y={34} fontSize={11} textAnchor="middle" fill="#888">
        {label}
      </text>
    </svg>
  )
}
