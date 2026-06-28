import { useEffect, useRef, useState } from 'react'
import { wsUrl } from '../api/client'
import type { Preview, WsMessage } from '../api/types'

export interface LiveState {
  wsConnected: boolean
  busy: boolean
  mode: string | null
  progress: number
  preview: Preview | null
}

export function useWebSocket(): LiveState {
  const [state, setState] = useState<LiveState>({
    wsConnected: false,
    busy: false,
    mode: null,
    progress: 0,
    preview: null,
  })
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const socket = new WebSocket(wsUrl())
    socketRef.current = socket

    socket.onopen = () => setState((s) => ({ ...s, wsConnected: true }))
    socket.onclose = () => setState((s) => ({ ...s, wsConnected: false }))
    socket.onmessage = (event: MessageEvent<string>) => {
      const msg = JSON.parse(event.data) as WsMessage
      if (msg.type === 'busy') {
        setState((s) => ({ ...s, busy: true, mode: msg.mode, progress: msg.progress }))
      } else if (msg.type === 'preview') {
        setState((s) => ({ ...s, preview: msg.data }))
      } else if (msg.type === 'state') {
        const idle = msg.data['instrument_state'] === 'idle'
        setState((s) => ({ ...s, busy: idle ? false : s.busy }))
      } else if (msg.type === 'progress') {
        const p = msg.data['progress']
        setState((s) => ({ ...s, progress: typeof p === 'number' ? p : s.progress }))
      }
    }

    return () => socket.close()
  }, [])

  return state
}
