interface Props {
  vendorConnected: boolean
  wsConnected: boolean
  busy: boolean
  error: string | null
}

export function StatusBanner({ vendorConnected, wsConnected, busy, error }: Props) {
  return (
    <div className="status-banner">
      <span className={vendorConnected ? 'ok' : 'err'}>
        vendor {vendorConnected ? 'connected' : 'disconnected'}
      </span>
      <span className={wsConnected ? 'ok' : 'err'}>ws {wsConnected ? 'live' : 'down'}</span>
      <span className={busy ? 'busy' : 'idle'}>{busy ? 'acquiring' : 'idle'}</span>
      {error && <span className="err">error: {error}</span>}
    </div>
  )
}
