import { describe, expect, it } from 'vitest'
import {
  buildChatRequestFromStream,
  streamMessagesToChatMessages,
} from './chatStreamHelpers'

describe('chatStreamHelpers', () => {
  it('keeps a single user message and a single assistant message for one streamed turn', () => {
    const previousMessages = [
      { id: 'user-1', role: 'user' as const, content: '你好', timestamp: 1 },
      { id: 'assistant-1', role: 'assistant' as const, content: '', timestamp: 2 },
    ]

    const streamMessages = [
      { id: 'user-1', getType: () => 'human', content: '你好' },
      { id: 'assistant-1', getType: () => 'ai', content: '' },
      { id: 'assistant-1', getType: () => 'ai', content: '你好呀' },
    ] as any

    const result = streamMessagesToChatMessages(streamMessages, previousMessages)

    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({ id: 'user-1', role: 'user', content: '你好' })
    expect(result[1]).toMatchObject({ id: 'assistant-1', role: 'assistant', content: '你好呀' })
  })

  it('dedupes duplicate latest user messages when building a chat request', () => {
    const request = buildChatRequestFromStream({
      historyMessages: [
        { id: 'user-0', type: 'human', content: '前文问题' },
        { id: 'assistant-0', type: 'ai', content: '前文回答' },
      ],
      inputMessages: [
        { id: 'user-1', type: 'human', content: '帮我总结一下' },
        { id: 'user-1', type: 'human', content: '帮我总结一下' },
      ],
      workspace: 'default',
      attachmentIds: [],
      source: 'chat_ui',
    })

    expect(request.query).toBe('帮我总结一下')
    expect(request.query_message_id).toBe('user-1')
    expect(request.history).toEqual([
      { id: 'user-0', role: 'user', content: '前文问题' },
      { id: 'assistant-0', role: 'assistant', content: '前文回答' },
    ])
  })
})
