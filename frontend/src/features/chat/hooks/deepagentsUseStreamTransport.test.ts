import { describe, expect, it } from 'vitest'
import { buildStreamFallbackId } from './deepagentsUseStreamTransport'

describe('deepagentsUseStreamTransport', () => {
  it('builds distinct fallback ids for id-less assistant messages in the same node', () => {
    const metadata = { langgraph_checkpoint_ns: 'root|model' }
    const message = { type: 'ai', content: 'hello' }

    const first = buildStreamFallbackId('thread-1', message, metadata, 1)
    const second = buildStreamFallbackId('thread-1', message, metadata, 2)

    expect(first).toBe('thread-1:ai:root|model:1')
    expect(second).toBe('thread-1:ai:root|model:2')
    expect(first).not.toBe(second)
  })
})
