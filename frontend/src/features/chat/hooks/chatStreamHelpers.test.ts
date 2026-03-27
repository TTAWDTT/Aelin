import { describe, expect, it } from 'vitest'
import {
  buildSessionHistoryMessages,
  formatBytes,
  trimQueryForApi,
} from './chatStreamHelpers'

describe('chatStreamHelpers', () => {
  it('formats attachment sizes for the composer', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
  })

  it('preserves multimodal human history messages', () => {
    const rows = buildSessionHistoryMessages([
      {
        id: 'user-1',
        role: 'user',
        content: '请看这张图',
        images: [{ dataUrl: 'data:image/png;base64,abc', name: 'demo.png' }],
        timestamp: Date.now(),
      },
    ])

    expect(rows).toHaveLength(1)
    expect(rows[0]?.id).toBe('user-1')
    expect(rows[0]?.type).toBe('human')
    expect(Array.isArray(rows[0]?.content)).toBe(true)
  })

  it('trims long prompts before submit payload assembly', () => {
    const source = 'a'.repeat(1300)
    const trimmed = trimQueryForApi(source)

    expect(trimmed.length).toBe(1200)
    expect(trimmed.endsWith('…')).toBe(true)
  })
})
