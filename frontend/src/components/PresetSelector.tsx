import { useCallback, useEffect, useState } from 'react'
import { deletePreset, listPresets, savePreset } from '../api/client'
import type { Preset } from '../api/types'

interface Props {
  mode: string
  currentParams: Record<string, unknown>
  onLoad: (params: Record<string, unknown>) => void
}

export function PresetSelector({ mode, currentParams, onLoad }: Props) {
  const [presets, setPresets] = useState<Preset[]>([])
  const [name, setName] = useState('')
  const [selected, setSelected] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    listPresets(mode)
      .then(setPresets)
      .catch(() => setPresets([]))
  }, [mode])

  useEffect(() => {
    refresh()
  }, [refresh])

  const onSave = async () => {
    if (!name.trim()) return
    setError(null)
    try {
      await savePreset(name.trim(), mode, currentParams)
      setName('')
      refresh()
    } catch (err: unknown) {
      setError(String(err))
    }
  }

  const onLoadSelected = () => {
    const preset = presets.find((p) => p.id === selected)
    if (preset) onLoad(preset.params)
  }

  const onDelete = async () => {
    if (!selected) return
    setError(null)
    try {
      await deletePreset(selected)
      setSelected('')
      refresh()
    } catch (err: unknown) {
      setError(String(err))
    }
  }

  return (
    <div className="preset-selector">
      <div className="preset-row">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">— presets —</option>
          {presets.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button type="button" disabled={!selected} onClick={onLoadSelected}>
          load
        </button>
        <button type="button" className="link" disabled={!selected} onClick={onDelete}>
          delete
        </button>
      </div>
      <div className="preset-row">
        <input
          type="text"
          placeholder="save current as…"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="button" disabled={!name.trim()} onClick={onSave}>
          save preset
        </button>
      </div>
      {error && <p className="warning">{error}</p>}
    </div>
  )
}
