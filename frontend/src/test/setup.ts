import '@testing-library/jest-dom'

// jsdom has no WebSocket; provide a no-op stub so components that open one render.
class MockWebSocket {
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  close() {}
  send() {}
}
// @ts-expect-error assigning a minimal stub to the global
globalThis.WebSocket = MockWebSocket
