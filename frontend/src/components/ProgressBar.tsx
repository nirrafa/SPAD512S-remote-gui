interface Props {
  value: number // 0..1
  visible: boolean
}

export function ProgressBar({ value, visible }: Props) {
  if (!visible) return null
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100)
  return (
    <div className="progress">
      <div className="progress-fill" style={{ width: `${pct}%` }} />
    </div>
  )
}
