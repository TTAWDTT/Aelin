import { describe, expect, it } from 'vitest'
import {
  buildSessionHistoryMessages,
  normalizeAssistantMarkdown,
} from './chatStreamHelpers'

describe('chatStreamHelpers', () => {
  it('normalizes markdown headings with a missing space', () => {
    expect(normalizeAssistantMarkdown('#Title\n##Subtitle')).toBe('# Title\n## Subtitle')
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
})
