import type { Roi, RoiStats } from '../utils/imageProcessing'

interface Row {
  roi: Roi
  stats: RoiStats
}

interface Props {
  rows: Row[]
  onRemove: (id: string) => void
}

export function RoiStatsTable({ rows, onRemove }: Props) {
  if (rows.length === 0) {
    return <p className="muted">No ROIs — pick a draw tool and drag on the image.</p>
  }
  return (
    <table className="roi-stats">
      <thead>
        <tr>
          <th>ROI</th>
          <th>Area (px)</th>
          <th>Mean</th>
          <th>Sum</th>
          <th>Max</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map(({ roi, stats }) => (
          <tr key={roi.id}>
            <td>{roi.label}</td>
            <td>{stats.area}</td>
            <td>{stats.mean.toFixed(1)}</td>
            <td>{stats.sum}</td>
            <td>{stats.max}</td>
            <td>
              <button type="button" className="link" onClick={() => onRemove(roi.id)}>
                remove
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
