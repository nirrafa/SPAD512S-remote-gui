import { describe, expect, it } from 'vitest'
import { applyColormap, decodeBase64 } from './colormap'

describe('colormap utils', () => {
  it('decodes base64 bytes round-trip', () => {
    const bytes = new Uint8Array([0, 128, 255])
    const b64 = btoa(String.fromCharCode(...bytes))
    expect(Array.from(decodeBase64(b64))).toEqual([0, 128, 255])
  })

  it('maps grayscale intensities to RGBA with opaque alpha', () => {
    const rgba = applyColormap(new Uint8Array([0, 255]), 'grayscale')
    expect(rgba.length).toBe(8)
    expect(Array.from(rgba.slice(0, 4))).toEqual([0, 0, 0, 255])
    expect(Array.from(rgba.slice(4, 8))).toEqual([255, 255, 255, 255])
  })

  it('produces colored output for viridis at the low end', () => {
    const rgba = applyColormap(new Uint8Array([0]), 'viridis')
    expect(Array.from(rgba.slice(0, 4))).toEqual([68, 1, 84, 255])
  })
})
