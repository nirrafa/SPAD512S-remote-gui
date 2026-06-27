import { render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from './App'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ json: () => Promise.resolve({ status: 'ok', version: '0.1.0' }) })),
  )
})

test('renders the app title', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: /SPAD512/i })).toBeInTheDocument()
})
