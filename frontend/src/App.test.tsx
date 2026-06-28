import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from './App'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string) => {
      const body =
        typeof input === 'string' && input.includes('/system/info')
          ? { sensor_size: 512, valid_bit_depths: [8], valid_roi_widths: [512], enabled_features: {} }
          : { vendor_connected: true, instrument_state: 'idle' }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) })
    }),
  )
})

test('renders the app title', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: /SPAD512/i })).toBeInTheDocument()
})
