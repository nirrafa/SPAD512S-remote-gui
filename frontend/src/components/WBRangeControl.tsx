import { autoStretchRange, type IntensityRange } from '../utils/imageProcessing'

interface Props {
  range: IntensityRange | null
  onChange: (range: IntensityRange | null) => void
  values?: Uint8Array | null
}

// Manual white-balance / contrast control: min/max display-stretch sliders
// (the movable "WB bar" the lab asked for — pulls faint DCR into visible
// range). Display-only; never touches the underlying data. `auto` seeds the
// sliders from the percentile stretch when pixel values are available.
export function WBRangeControl({ range, onChange, values }: Props) {
  const min = range?.min ?? 0
  const max = range?.max ?? 255
  const hasValues = values != null && values.length > 0

  return (
    <div className="wb-control" role="group" aria-label="White balance">
      <span className="muted">WB</span>
      <input
        type="range"
        min={0}
        max={254}
        value={min}
        aria-label="WB min"
        onChange={(e) => {
          const v = Number(e.target.value)
          onChange({ min: v, max: Math.max(max, v + 1) })
        }}
      />
      <input
        type="range"
        min={1}
        max={255}
        value={max}
        aria-label="WB max"
        onChange={(e) => {
          const v = Number(e.target.value)
          onChange({ min: Math.min(min, v - 1), max: v })
        }}
      />
      <button
        type="button"
        data-testid="auto-stretch"
        disabled={!hasValues}
        onClick={() => {
          if (values != null && values.length > 0) onChange(autoStretchRange(values))
        }}
      >
        auto
      </button>
      <button type="button" className="link" disabled={!range} onClick={() => onChange(null)}>
        reset
      </button>
      {range && (
        <span className="muted">
          range {range.min}–{range.max}
        </span>
      )}
    </div>
  )
}
