import type { BaseMessage } from '@langchain/core/messages'

export type ChatStreamState = {
  messages: Array<Record<string, unknown>>
  topology?: Record<string, unknown>
  answer?: string
  todos?: unknown[]
  [key: string]: unknown
}

export type ChatRuntimeStream = {
  messages: BaseMessage[]
  values?: ChatStreamState
  isLoading: boolean
  toolCalls?: unknown[]
  activeSubagents?: unknown[]
  subagents?: Map<string, unknown>
  getToolCalls?: (message: BaseMessage) => unknown[]
  getSubagentsByMessage?: (messageId: string) => unknown[]
  getMessagesMetadata: (
    message: BaseMessage,
    index?: number,
  ) => {
    messageId?: string
    branch?: string
    streamMetadata?: Record<string, unknown>
  } | undefined
}

export type ExecutionTopologyNode = {
  id: string
  name: string
  kind: string
  depth: number
  visits: number
  toolCalls: number
  subagents: number
  status: 'idle' | 'completed' | 'running'
}

export type ExecutionTopologyEdge = {
  source: string
  target: string
  conditional?: boolean
  active: boolean
  traversed: number
}

type BaseTopologyEdge = {
  source: string
  target: string
  conditional: boolean
}

export type ExecutionToolCall = {
  key: string
  name: string
  state: string
  args: string
  result: string
}

export type ExecutionSubagent = {
  key: string
  name: string
  type: string
  status: string
  depth: number
  messageCount: number
}

export type ExecutionTurn = {
  key: string
  messageId: string
  node: string
  namespace: string
  preview: string
  status: string
  toolCalls: ExecutionToolCall[]
  subagents: ExecutionSubagent[]
  isStreaming: boolean
}

export type ExecutionRuntime = {
  topology: {
    nodes: ExecutionTopologyNode[]
    edges: ExecutionTopologyEdge[]
  }
  turns: ExecutionTurn[]
  tools: ExecutionToolCall[]
  subagents: ExecutionSubagent[]
  hasExecution: boolean
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function compactText(value: unknown, max = 140): string {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function stableJson(value: unknown, max = 180): string {
  try {
    return compactText(JSON.stringify(value), max)
  } catch {
    return compactText(value, max)
  }
}

function messageTypeOf(message: BaseMessage): string {
  const value =
    typeof (message as any)?.getType === 'function'
      ? (message as any).getType()
      : (message as any)?.type
  return String(value || '').trim().toLowerCase()
}

function messagePreview(message: BaseMessage): string {
  const content = (message as any)?.content
  if (typeof content === 'string') return compactText(content)
  if (Array.isArray(content)) {
    const joined = content
      .map((item) => {
        const record = asRecord(item)
        if (record.type === 'text') return String(record.text || '')
        return ''
      })
      .filter(Boolean)
      .join(' ')
    return compactText(joined)
  }
  return ''
}

function normalizeStatus(value: unknown, fallback = 'idle'): string {
  const text = String(value || '').trim().toLowerCase()
  return text || fallback
}

function computeDepths(
  nodes: Array<{ id: string }>,
  edges: Array<{ source: string; target: string }>,
): Map<string, number> {
  const indegree = new Map<string, number>()
  const outgoing = new Map<string, string[]>()

  for (const node of nodes) {
    indegree.set(node.id, 0)
    outgoing.set(node.id, [])
  }

  for (const edge of edges) {
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge.target])
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
  }

  const queue = nodes
    .filter((node) => (indegree.get(node.id) ?? 0) === 0)
    .map((node) => node.id)
  const depth = new Map<string, number>()

  for (const id of queue) depth.set(id, 0)

  while (queue.length > 0) {
    const current = queue.shift()!
    const currentDepth = depth.get(current) ?? 0
    for (const next of outgoing.get(current) ?? []) {
      depth.set(next, Math.max(depth.get(next) ?? 0, currentDepth + 1))
      indegree.set(next, (indegree.get(next) ?? 1) - 1)
      if ((indegree.get(next) ?? 0) <= 0) queue.push(next)
    }
  }

  for (const node of nodes) {
    if (!depth.has(node.id)) depth.set(node.id, 0)
  }

  return depth
}

function buildExecutionTopology(
  raw: Record<string, unknown>,
  turns: ExecutionTurn[],
): {
  nodes: ExecutionTopologyNode[]
  edges: ExecutionTopologyEdge[]
} {
  const rawNodes = Array.isArray(raw.nodes) ? raw.nodes : []
  const rawEdges: BaseTopologyEdge[] = (Array.isArray(raw.edges) ? raw.edges : [])
    .map((item) => {
      const record = asRecord(item)
      const source = String(record.source || '').trim()
      const target = String(record.target || '').trim()
      if (!source || !target) return null
      return {
        source,
        target,
        conditional: Boolean(record.conditional),
      }
    })
    .filter((item): item is BaseTopologyEdge => item != null)

  const latestTurn = turns.at(-1)
  const baseNodes = rawNodes
    .map((item) => {
      const record = asRecord(item)
      const id = String(record.id || '').trim()
      if (!id) return null
      return {
        id,
        name: String(record.name || id),
        kind: String(record.kind || 'node'),
      }
    })
    .filter((item): item is { id: string; name: string; kind: string } => item != null)
  const depths = computeDepths(baseNodes, rawEdges)
  const nodeIds = new Set(baseNodes.map((node) => node.id))
  const turnNodeKeys = turns.map((turn) => turn.node).filter((node) => nodeIds.has(node))
  const turnCounts = new Map<string, number>()
  const toolCallCounts = new Map<string, number>()
  const subagentCounts = new Map<string, number>()
  const edgeTraversals = new Map<string, number>()

  for (const turn of turns) {
    if (!nodeIds.has(turn.node)) continue
    turnCounts.set(turn.node, (turnCounts.get(turn.node) ?? 0) + 1)
    toolCallCounts.set(turn.node, (toolCallCounts.get(turn.node) ?? 0) + turn.toolCalls.length)
    subagentCounts.set(turn.node, (subagentCounts.get(turn.node) ?? 0) + turn.subagents.length)
  }

  for (let index = 0; index < turnNodeKeys.length - 1; index += 1) {
    const source = turnNodeKeys[index]
    const target = turnNodeKeys[index + 1]
    const edgeKey = `${source}->${target}`
    edgeTraversals.set(edgeKey, (edgeTraversals.get(edgeKey) ?? 0) + 1)
  }

  return {
    nodes: baseNodes.map((node) => ({
      ...node,
      depth: depths.get(node.id) ?? 0,
      visits: turnCounts.get(node.id) ?? 0,
      toolCalls: toolCallCounts.get(node.id) ?? 0,
      subagents: subagentCounts.get(node.id) ?? 0,
      status: latestTurn?.node === node.id
        ? 'running'
        : (turnCounts.get(node.id) ?? 0) > 0
          ? 'completed'
          : 'idle',
    })),
    edges: rawEdges.map((edge) => {
      const traversed = edgeTraversals.get(`${edge.source}->${edge.target}`) ?? 0
      return {
        ...edge,
        traversed,
        active:
          traversed > 0
          || (
            latestTurn != null
            && (latestTurn.node === edge.source || latestTurn.node === edge.target)
          ),
      }
    }),
  }
}

function getMessageId(message: BaseMessage, metadataMessageId: string | undefined, index: number): string {
  const direct = String((message as any)?.id || '').trim()
  if (direct) return direct
  const meta = String(metadataMessageId || '').trim()
  if (meta) return meta
  return `message:${index}`
}

function getToolCallsForMessage(stream: ChatRuntimeStream, message: BaseMessage): ExecutionToolCall[] {
  if (!stream.getToolCalls) return []
  return (stream.getToolCalls(message) ?? []).map((item, index) => {
    const record = asRecord(item)
    const call = asRecord(record.call)
    const result = record.result
    const name = String(call.name || record.name || 'tool').trim() || 'tool'
    return {
      key: String(record.id || call.id || `${name}:${index}`),
      name,
      state: normalizeStatus(record.status || record.state, result == null ? 'running' : 'completed'),
      args: call.args == null ? '' : stableJson(call.args, 160),
      result: result == null ? '' : stableJson(result, 180),
    }
  })
}

function getSubagentsForMessage(stream: ChatRuntimeStream, messageId: string): ExecutionSubagent[] {
  if (!stream.getSubagentsByMessage) return []
  const rows = stream.getSubagentsByMessage(messageId)
  if (!Array.isArray(rows)) return []
  return rows.map((item, index) => {
    const record = item as unknown as Record<string, unknown>
    const messages = Array.isArray(record.messages) ? record.messages : []
    return {
      key: String(record.id || record.toolCallId || `subagent:${messageId}:${index}`),
      name: String(record.name || record.subagent_type || 'subagent'),
      type: String(record.subagent_type || record.type || 'subagent'),
      status: normalizeStatus(record.status, 'idle'),
      depth: Number(record.depth || 1),
      messageCount: messages.length,
    }
  })
}

export function getExecutionTurns(stream: ChatRuntimeStream): ExecutionTurn[] {
  return stream.messages
    .map((message, index) => {
      const metadata = stream.getMessagesMetadata(message, index)
      const streamMetadata = asRecord(metadata?.streamMetadata)
      const node = String(streamMetadata.langgraph_node || '').trim()
      const messageType = messageTypeOf(message)
      const messageId = getMessageId(message, metadata?.messageId, index)
      const toolCalls = getToolCallsForMessage(stream, message)
      const subagents = getSubagentsForMessage(stream, messageId)
      const preview = messagePreview(message)
      const namespace = String(
        streamMetadata.langgraph_checkpoint_ns
        || streamMetadata.checkpoint_ns
        || metadata?.branch
        || 'root',
      )

      if (
        !node
        && toolCalls.length === 0
        && subagents.length === 0
        && messageType !== 'ai'
      ) {
        return null
      }

      const hasWork = toolCalls.length > 0 || subagents.length > 0 || Boolean(node)
      if (!hasWork) return null

      return {
        key: `${messageId}:${node || 'turn'}`,
        messageId,
        node: node || messageType || 'message',
        namespace,
        preview,
        status: stream.isLoading && index === stream.messages.length - 1 ? 'running' : 'completed',
        toolCalls,
        subagents,
        isStreaming: stream.isLoading && index === stream.messages.length - 1,
      }
    })
    .filter((item): item is ExecutionTurn => item != null)
}

export function getExecutionRuntime(stream: ChatRuntimeStream): ExecutionRuntime {
  const turns = getExecutionTurns(stream)
  const topology = buildExecutionTopology(asRecord(stream.values?.topology), turns)
  const tools = turns.flatMap((turn) => turn.toolCalls)
  const subagents = turns.flatMap((turn) => turn.subagents)
  const hasExecution =
    topology.nodes.length > 0
    || turns.length > 0
    || Object.keys(asRecord(stream.values)).some((key) => key !== 'messages')

  return {
    topology,
    turns,
    tools,
    subagents,
    hasExecution,
  }
}

export function summarizeExecutionStatus(
  runtime: ExecutionRuntime,
  options: {
    isLoading: boolean
    fallback: string
  },
): string {
  const { turns, tools, subagents } = runtime
  const runningSubagents = subagents.filter((item) => item.status === 'running' || item.status === 'pending').length
  if (runningSubagents > 0) {
    return runningSubagents === 1
      ? '正在运行 1 个子代理…'
      : `正在运行 ${runningSubagents} 个子代理…`
  }

  const activeTools = tools.filter((item) => item.state === 'running' || item.state === 'pending')
  if (activeTools.length > 0) {
    return `正在调用工具… ${activeTools.slice(0, 3).map((item) => item.name).join(' · ')}`
  }

  const last = turns.at(-1)
  if (options.isLoading && last?.node) {
    return `正在执行 ${last.node}…`
  }

  return options.fallback
}
