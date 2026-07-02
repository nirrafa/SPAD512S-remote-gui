interface Props {
  label: string
  value: number
  unit?: string
  threshold?: number
}

export function TemperatureGauge({ label, value, unit = '°C', threshold }: Props) {
  const over = threshold !== undefined && value > threshold
  return (
    <div className={over ? 'gauge gauge-alarm' : 'gauge'}>
      <span className="gauge-label">{label}</span>
      <span className="gauge-value">
        {value.toFixed(1)}
        {unit}
      </span>
    </div>
  )
}
