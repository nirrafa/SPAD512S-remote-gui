interface Props {
  count: number
  value: number
  onChange: (step: number) => void
}

export function GateStepSlider({ count, value, onChange }: Props) {
  if (count <= 1) return null
  return (
    <div className="gate-slider">
      <label>
        Gate step {value + 1} / {count}
        <input
          type="range"
          min={0}
          max={count - 1}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </label>
    </div>
  )
}
