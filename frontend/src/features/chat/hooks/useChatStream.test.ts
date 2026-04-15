import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BaseMessage } from '@langchain/core/messages'
import type { ChatSessionRuntime } from '../stores/chatStore'

type RuntimeMetadataReader =
  | ((
      message: BaseMessage,
      index?: number,
    ) => {
      messageId?: string
      branch?: string
      streamMetadata?: Record<string, unknown>
    } | undefined)
  | undefined

const sessionMessages = [
  {
    id: 'persisted-1',
    role: 'assistant' as const,
    content: 'persisted answer',
    timestamp: 1,
  },
]

const mocks = vi.hoisted(() => {
  const clientStub = { tag: 'client-stub' }
  const streamMock = {
    messages: [] as BaseMessage[],
    values: { messages: [] as Array<Record<string, unknown>> },
    isLoading: false,
    subagents: new Map(),
    getToolCalls: undefined as (((message: BaseMessage) => unknown[]) | undefined),
    getMessagesMetadata: undefined as RuntimeMetadataReader,
    submit: vi.fn(),
    stop: vi.fn(),
    switchThread: vi.fn(),
    tryReconnect: vi.fn(() => false),
  }

  const ensureRuntime = (sessionId: string): ChatSessionRuntime => {
    const existing = storeState.sessionRuntimeById[sessionId]
    if (existing) return existing
    const nextRuntime: ChatSessionRuntime = {
      phase: 'idle',
      statusText: '',
      lastErrorCode: null,
    }
    storeState.sessionRuntimeById[sessionId] = nextRuntime
    return nextRuntime
  }

  const storeState = {
    sessions: [
      { id: 'session-1', title: 'Session 1', createdAt: 1, workspace: 'research' },
    ],
    activeSessionId: 'session-1' as string | null,
    sessionRuntimeById: {} as Record<string, ChatSessionRuntime>,
    createSession: vi.fn(() => 'session-created'),
    setSessionStatusText: vi.fn((sessionId: string, value: string) => {
      ensureRuntime(sessionId).statusText = value
    }),
    setSessionLastErrorCode: vi.fn((sessionId: string, value: string | null) => {
      ensureRuntime(sessionId).lastErrorCode = value
    }),
    setSessionPhase: vi.fn((sessionId: string, value: ChatSessionRuntime['phase']) => {
      ensureRuntime(sessionId).phase = value
    }),
    clearSessionRuntime: vi.fn((sessionId: string) => {
      delete storeState.sessionRuntimeById[sessionId]
    }),
    renameSession: vi.fn(),
  }

  const useChatStoreMock = Object.assign(
    (selector: (state: typeof storeState) => unknown) => selector(storeState),
    {
      getState: () => storeState,
    },
  )

  return {
    clientStub,
    streamMock,
    storeState,
    useChatStoreMock,
    useStreamMock: vi.fn(() => streamMock),
    ensureThreadExistsMock: vi.fn(() => Promise.resolve()),
    findAssistantIdMock: vi.fn(() => Promise.resolve('assistant-1')),
    fetchAssistantGraphMock: vi.fn(() => Promise.resolve(null)),
    setSessionMessagesMock: vi.fn(),
  }
})

vi.mock('@langchain/react', () => ({
  useStream: mocks.useStreamMock,
}))

vi.mock('@langchain/langgraph-sdk', () => ({
  Client: function Client() {
    return mocks.clientStub
  },
}))

vi.mock('../stores/chatStore', () => ({
  useChatStore: mocks.useChatStoreMock,
  selectSessionRuntime: (
    state: { sessionRuntimeById: Record<string, ChatSessionRuntime> },
    sessionId: string | null | undefined,
  ) => {
    const id = String(sessionId || '').trim()
    return id
      ? (state.sessionRuntimeById[id] ?? {
          phase: 'idle' as const,
          statusText: '',
          lastErrorCode: null,
        })
      : {
          phase: 'idle' as const,
          statusText: '',
          lastErrorCode: null,
        }
  },
}))

vi.mock('../chatI18n', () => ({
  useChatI18n: () => ({
    t: (key: string) => {
      if (key === 'status.thinking') return '思考中'
      if (key === 'status.cancelled') return '已取消'
      if (key === 'status.capture.region') return '截图中'
      if (key === 'status.capture.fullscreen') return '截图中'
      if (key === 'status.attach.processing') return '处理中'
      if (key === 'session.running') return '后台运行中'
      return key
    },
  }),
}))

vi.mock('../chatHistoryStorage', () => ({
  getSessionMessages: vi.fn(() => sessionMessages),
  setSessionMessages: mocks.setSessionMessagesMock,
}))

vi.mock('./chatStreamRuntime', () => ({
  ensureThreadExists: mocks.ensureThreadExistsMock,
  fetchAssistantGraph: mocks.fetchAssistantGraphMock,
  findAssistantId: mocks.findAssistantIdMock,
}))

vi.mock('@/shared/api/aelin', () => ({
  aelinApi: {
    deviceScreenCapture: vi.fn(),
    uploadAttachment: vi.fn(),
  },
}))

import { useChatStream } from './useChatStream'

function renderHook(): ReturnType<typeof useChatStream> {
  let captured: ReturnType<typeof useChatStream> | null = null

  function Harness() {
    captured = useChatStream()
    return React.createElement('div')
  }

  renderToStaticMarkup(React.createElement(Harness))
  const result = captured
  if (!result) throw new Error('failed to render useChatStream')
  return result as ReturnType<typeof useChatStream>
}

function createMessage(
  id: string,
  role: 'human' | 'ai',
  content: string,
): BaseMessage {
  return {
    id,
    content,
    getType: () => role,
  } as BaseMessage
}

describe('useChatStream', () => {
  beforeEach(() => {
    mocks.streamMock.messages = []
    mocks.streamMock.values = { messages: [] }
    mocks.streamMock.isLoading = false
    mocks.streamMock.subagents = new Map()
    mocks.streamMock.getToolCalls = undefined
    mocks.streamMock.getMessagesMetadata = undefined
    mocks.streamMock.submit.mockReset()
    mocks.streamMock.stop.mockReset()
    mocks.streamMock.switchThread.mockReset()
    mocks.streamMock.tryReconnect.mockReset()
    mocks.streamMock.tryReconnect.mockReturnValue(false)
    mocks.useStreamMock.mockClear()
    mocks.ensureThreadExistsMock.mockClear()
    mocks.findAssistantIdMock.mockClear()
    mocks.fetchAssistantGraphMock.mockClear()
    mocks.setSessionMessagesMock.mockClear()
    mocks.storeState.sessions = [
      { id: 'session-1', title: 'Session 1', createdAt: 1, workspace: 'research' },
    ]
    mocks.storeState.activeSessionId = 'session-1'
    mocks.storeState.sessionRuntimeById = {}
    mocks.storeState.createSession.mockClear()
    mocks.storeState.renameSession.mockClear()
    mocks.storeState.setSessionStatusText.mockClear()
    mocks.storeState.setSessionLastErrorCode.mockClear()
    mocks.storeState.setSessionPhase.mockClear()
    mocks.storeState.clearSessionRuntime.mockClear()
  })

  it('configures official useStream as the runtime source', () => {
    renderHook()

    expect(mocks.useStreamMock).toHaveBeenCalledWith(
      expect.objectContaining({
        assistantId: '__aelin_agent_pending__',
        threadId: null,
        reconnectOnMount: true,
        messagesKey: 'messages',
        filterSubagentMessages: true,
        initialValues: {
          messages: expect.any(Array),
        },
      }),
    )
  })

  it('projects runtime messages from useStream instead of persisted history', () => {
    mocks.streamMock.messages = [
      createMessage('user-1', 'human', '你好'),
      createMessage('assistant-1', 'ai', '你好，我在这里。'),
    ]

    const hook = renderHook()

    expect(hook.messages).toEqual([
      expect.objectContaining({ id: 'user-1', role: 'user', content: '你好' }),
      expect.objectContaining({ id: 'assistant-1', role: 'assistant', content: '你好，我在这里。' }),
    ])
  })

  it('keeps assistant runtime messages that only expose tool calls through the official helper', () => {
    mocks.streamMock.messages = [
      createMessage('assistant-tools', 'ai', ''),
    ]
    mocks.streamMock.getToolCalls = vi.fn(() => [
      {
        id: 'call-1',
        status: 'completed',
        call: {
          id: 'call-1',
          name: 'render_poster_artifact',
          args: { brief: '同济大学樱花季海报' },
        },
        result: {
          artifact_count: 2,
        },
      },
    ])

    const hook = renderHook()

    expect(hook.messages).toEqual([
      expect.objectContaining({
        id: 'assistant-tools',
        role: 'assistant',
        content: '',
      }),
    ])
  })

  it('uses official metadata message ids so tool-call keyed artifacts can attach to the same bubble', () => {
    mocks.streamMock.messages = [
      {
        content: '',
        getType: () => 'ai',
      } as BaseMessage,
    ]
    mocks.streamMock.getToolCalls = vi.fn(() => [
      {
        id: 'call-1',
        status: 'completed',
        call: {
          id: 'call-1',
          name: 'render_poster_artifact',
          args: { brief: '同济大学樱花季海报' },
        },
        result: {
          artifact_count: 2,
        },
      },
    ])
    mocks.streamMock.getMessagesMetadata = vi.fn(() => ({
      messageId: 'official-msg-1',
    }))

    const hook = renderHook()

    expect(hook.messages).toEqual([
      expect.objectContaining({
        id: 'official-msg-1',
        role: 'assistant',
        content: '',
      }),
    ])
  })

  it('submits a minimal official payload and delegates stop to useStream', async () => {
    const hook = renderHook()
    mocks.findAssistantIdMock.mockResolvedValue('')

    await hook.send('帮我查一下', undefined, [7, 7, 0, -1, 9])

    expect(mocks.ensureThreadExistsMock).toHaveBeenCalledWith(mocks.clientStub, 'session-1')
    expect(mocks.findAssistantIdMock).toHaveBeenCalledWith(mocks.clientStub)
    expect(mocks.streamMock.switchThread).toHaveBeenCalledWith('session-1')
    expect(mocks.streamMock.tryReconnect).toHaveBeenCalledTimes(1)
    expect(mocks.streamMock.submit).toHaveBeenCalledTimes(1)

    const [payload, options] = mocks.streamMock.submit.mock.calls[0]
    expect(payload.messages).toHaveLength(1)
    expect(payload.messages[0]).toEqual(
      expect.objectContaining({
        type: 'human',
        content: '帮我查一下',
      }),
    )
    expect(Object.keys(options.context).sort()).toEqual(['attachment_ids', 'source', 'workspace'])
    expect(options.context).toEqual({
      workspace: 'research',
      source: 'chat_ui',
      attachment_ids: [7, 9],
    })
    expect(options.streamSubgraphs).toBe(true)
    expect(options.onDisconnect).toBe('continue')
    expect(options.streamResumable).toBe(true)
    expect(options.optimisticValues({ messages: [{ id: 'persisted-1', type: 'ai', content: 'persisted answer' }] }))
      .toEqual({
        messages: [
          { id: 'persisted-1', type: 'ai', content: 'persisted answer' },
          expect.objectContaining({ type: 'human', content: '帮我查一下' }),
        ],
      })

    hook.stop()
    expect(mocks.streamMock.stop).toHaveBeenCalledTimes(1)
    expect(mocks.storeState.setSessionStatusText).toHaveBeenCalledWith('session-1', '已取消')
    expect(mocks.storeState.setSessionPhase).toHaveBeenCalledWith('session-1', 'idle')
  })
})
