import { useEffect, useRef, useState } from 'react'
import { wsUrl } from '../api/client'
import type { Preview, WsMessage } from '../api/types'

export interface LiveState {
  wsConnected: boolean
  busy: boolean
  mode: string | null
  progress: number
  preview: Preview | null
  stepPreviews: (Preview | null)[]
  stepCount: number
}

interface PreviewMessage {
  type: 'preview'
  data: Preview
  index?: number
  count?: number
}

const INITIAL: LiveState = {
  wsConnected: false,
  busy: false,
  mode: null,
  progress: 0,
  preview: null,
  stepPreviews: [],
  stepCount: 0,
}

export function useWebSocket(): LiveState {
  const [state, setState] = useState<LiveState>(INITIAL)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let unmounted = false
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let backoff = 500

    const connect = () => {
      const socket = new WebSocket(wsUrl())
      socketRef.current = socket

      socket.onopen = () => {
        backoff = 500
        setState((s) => ({ ...s, wsConnected: true }))
      }
      socket.onclose = () => {
        setState((s) => ({ ...s, wsConnected: false }))
        if (!unmounted) {
          reconnectTimer = setTimeout(connect, backoff)
          backoff = Math.min(backoff * 2, 10000)
        }
      }
      socket.onmessage = (event: MessageEvent<string>) => {
        let msg: WsMessage
        try {
          msg = JSON.parse(event.data) as WsMessage
        } catch {
          return
        }
        if (msg.type === 'busy') {
          // New acquisition: reset any collected per-step previews.
          setState((s) => ({
            ...s,
            busy: true,
            mode: msg.mode,
            progress: msg.progress,
            stepPreviews: [],
            stepCount: 0,
          }))
        } else if (msg.type === 'preview') {
          const pm = msg as PreviewMessage
          setState((s) => {
            if (pm.index === undefined) return { ...s, preview: pm.data }
            const count = pm.count ?? Math.max(s.stepCount, pm.index + 1)
            const stepPreviews = s.stepPreviews.slice()
            while (stepPreviews.length < count) stepPreviews.push(null)
            stepPreviews[pm.index] = pm.data
            return { ...s, preview: pm.data, stepPreviews, stepCount: count }
          })
        } else if (msg.type === 'state') {
          const idle = msg.data['instrument_state'] === 'idle'
          setState((s) => ({ ...s, busy: idle ? false : s.busy }))
        } else if (msg.type === 'progress') {
          const p = msg.data['progress']
          setState((s) => ({ ...s, progress: typeof p === 'number' ? p : s.progress }))
        }
      }
    }

    connect()
    return () => {
      unmounted = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socketRef.current?.close()
    }
  }, [])

  return state
}
