export type ColormapName = 'grayscale' | 'viridis' | 'inferno' | 'plasma'

type RGB = [number, number, number]

const STOPS: Record<ColormapName, RGB[]> = {
  grayscale: [
    [0, 0, 0],
    [255, 255, 255],
  ],
  viridis: [
    [68, 1, 84],
    [59, 82, 139],
    [33, 145, 140],
    [94, 201, 98],
    [253, 231, 37],
  ],
  inferno: [
    [0, 0, 4],
    [87, 16, 110],
    [188, 55, 84],
    [249, 142, 9],
    [252, 255, 164],
  ],
  plasma: [
    [13, 8, 135],
    [126, 3, 168],
    [204, 71, 120],
    [248, 149, 64],
    [240, 249, 33],
  ],
}

function buildLut(stops: RGB[]): Uint8Array {
  const lut = new Uint8Array(256 * 3)
  const segments = stops.length - 1
  for (let i = 0; i < 256; i++) {
    const t = (i / 255) * segments
    const lo = Math.min(Math.floor(t), segments - 1)
    const frac = t - lo
    const a = stops[lo] ?? [0, 0, 0]
    const b = stops[lo + 1] ?? a
    lut[i * 3] = Math.round(a[0] + (b[0] - a[0]) * frac)
    lut[i * 3 + 1] = Math.round(a[1] + (b[1] - a[1]) * frac)
    lut[i * 3 + 2] = Math.round(a[2] + (b[2] - a[2]) * frac)
  }
  return lut
}

const LUTS: Record<ColormapName, Uint8Array> = {
  grayscale: buildLut(STOPS.grayscale),
  viridis: buildLut(STOPS.viridis),
  inferno: buildLut(STOPS.inferno),
  plasma: buildLut(STOPS.plasma),
}

export const COLORMAP_NAMES: ColormapName[] = ['grayscale', 'viridis', 'inferno', 'plasma']

/** Decode a base64 string of raw uint8 bytes into a typed array. */
export function decodeBase64(data: string): Uint8Array {
  const binary = atob(data)
  const out = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    out[i] = binary.charCodeAt(i)
  }
  return out
}

/** Map an array of 0–255 intensities to RGBA pixels via the named colormap. */
export function applyColormap(values: Uint8Array, name: ColormapName): Uint8ClampedArray {
  const lut = LUTS[name]
  const rgba = new Uint8ClampedArray(values.length * 4)
  for (let i = 0; i < values.length; i++) {
    const v = (values[i] ?? 0) * 3
    rgba[i * 4] = lut[v] ?? 0
    rgba[i * 4 + 1] = lut[v + 1] ?? 0
    rgba[i * 4 + 2] = lut[v + 2] ?? 0
    rgba[i * 4 + 3] = 255
  }
  return rgba
}
