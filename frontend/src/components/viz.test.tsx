import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DCRCurveChart } from './DCRCurveChart'
import { DecayCurve } from './DecayCurve'
import { PhasorScatter } from './PhasorScatter'
import { PixelHistogram } from './PixelHistogram'

// These render tests lock in the DOM ids the PRD §7 spec (test_10) targets, so
// the deferred Playwright gate has stable anchors.

describe('visualization DOM anchors', () => {
  it('pixel histogram exposes #pixel-histogram once it has data', () => {
    const values = new Uint8Array([1, 2, 3, 200, 255])
    const { container } = render(<PixelHistogram values={values} />)
    expect(container.querySelector('#pixel-histogram')).not.toBeNull()
  })

  it('phasor plot exposes #phasor-plot even when empty', () => {
    const { container } = render(<PhasorScatter phasor={{ g: [0.4], s: [0.3] }} />)
    expect(container.querySelector('#phasor-plot')).not.toBeNull()
  })

  it('decay curve exposes #decay-curve with series data', () => {
    const { container } = render(
      <DecayCurve gateOffsets={[0, 18, 36]} series={[{ label: 'A', counts: [10, 6, 3] }]} />,
    )
    expect(container.querySelector('#decay-curve')).not.toBeNull()
  })

  it('DCR chart exposes #dcr-curve with values', () => {
    const { container } = render(
      <DCRCurveChart curve={{ percentages: [0, 50, 100], dcr_values: [5, 3, 1] }} />,
    )
    expect(container.querySelector('#dcr-curve')).not.toBeNull()
  })
})
