import { describe, expect, it } from 'vitest'
import {
  buildHumanStreamMessage,
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

  it('keeps image-only human messages as multimodal blocks', () => {
    const row = buildHumanStreamMessage('', [
      { dataUrl: 'data:image/png;base64,abc', name: 'demo.png' },
    ], 'user-image-only')

    expect(row.id).toBe('user-image-only')
    expect(row.type).toBe('human')
    expect(row.content).toEqual([
      {
        type: 'image_url',
        image_url: { url: 'data:image/png;base64,abc' },
      },
    ])
  })

  it('trims long prompts before submit payload assembly', () => {
    const source = 'a'.repeat(1300)
    const trimmed = trimQueryForApi(source)

    expect(trimmed.length).toBe(1200)
    expect(trimmed.endsWith('…')).toBe(true)
  })
})
