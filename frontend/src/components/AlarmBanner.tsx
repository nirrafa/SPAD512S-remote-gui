import type { Alarm } from '../api/types'

interface Props {
  alarms: Alarm[]
}

const LABELS: Record<string, string> = {
  over_temperature: 'Over-temperature',
  cooling_failure: 'Cooling failure',
  missing_laser_trigger: 'Missing laser trigger',
  abnormal_laser_trigger: 'Abnormal laser trigger',
  suspected_overexposure: 'Suspected overexposure',
  vex_reduced: 'Excess bias reduced for safety',
}

export function AlarmBanner({ alarms }: Props) {
  if (alarms.length === 0) {
    return <div className="alarms alarms-clear">No active alarms.</div>
  }
  return (
    <ul className="alarms">
      {alarms.map((a) => (
        <li key={a.type} className={`alarm alarm-${a.severity ?? 'warning'}`}>
          <span className="alarm-type">{LABELS[a.type] ?? a.type}</span>
          {a.value !== undefined && <span className="alarm-value">{a.value}</span>}
        </li>
      ))}
    </ul>
  )
}
