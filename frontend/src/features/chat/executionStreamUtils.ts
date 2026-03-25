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
  active: boolean
}

export type ExecutionTopologyEdge = {
  source: string
  target: string
}

export type ExecutionStep = {
  key: string
  node: string
  namespace: string
  messageType: string
  preview: string
  active: boolean
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
  edges: ExecutionTopologyEdge[],
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

export function getExecutionTopology(stream: ChatRuntimeStream): {
  nodes: ExecutionTopologyNode[]
  edges: ExecutionTopologyEdge[]
} {
  const raw = asRecord(stream.values?.topology)
  const rawNodes = Array.isArray(raw.nodes) ? raw.nodes : []
  const edges = (Array.isArray(raw.edges) ? raw.edges : [])
    .map((item) => {
      const record = asRecord(item)
      const source = String(record.source || '').trim()
      const target = String(record.target || '').trim()
      if (!source || !target) return null
      return { source, target }
    })
    .filter((item): item is ExecutionTopologyEdge => item != null)

  const activeNodeKeys = new Set(getExecutionSteps(stream).map((item) => item.node))
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
  const depths = computeDepths(baseNodes, edges)

  return {
    nodes: baseNodes.map((node) => ({
      ...node,
      depth: depths.get(node.id) ?? 0,
      active: activeNodeKeys.has(node.id),
    })),
    edges,
  }
}

export function getExecutionSteps(stream: ChatRuntimeStream): ExecutionStep[] {
  return stream.messages
    .map((message, index) => {
      const metadata = stream.getMessagesMetadata(message, index)
      const streamMetadata = asRecord(metadata?.streamMetadata)
      const node = String(streamMetadata.langgraph_node || '').trim()
      if (!node) return null

      const namespace = String(
        streamMetadata.langgraph_checkpoint_ns
        || streamMetadata.checkpoint_ns
        || metadata?.branch
        || 'root',
      )

      return {
        key: `${metadata?.messageId || index}:${node}:${namespace}`,
        node,
        namespace,
        messageType: messageTypeOf(message),
        preview: messagePreview(message),
        active: index === stream.messages.length - 1 && stream.isLoading,
      }
    })
    .filter((item): item is ExecutionStep => item != null)
}

export function getExecutionToolCalls(stream: ChatRuntimeStream): ExecutionToolCall[] {
  return (stream.toolCalls ?? []).map((item, index) => {
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

export function getExecutionSubagents(stream: ChatRuntimeStream): ExecutionSubagent[] {
  return [...(stream.subagents?.values() ?? [])].map((item, index) => {
    const record = item as unknown as Record<string, unknown>
    const messages = Array.isArray(record.messages) ? record.messages : []
    return {
      key: String(record.id || record.toolCallId || `subagent:${index}`),
      name: String(record.name || record.subagent_type || 'subagent'),
      type: String(record.subagent_type || record.type || 'subagent'),
      status: normalizeStatus(record.status, 'idle'),
      depth: Number(record.depth || 1),
      messageCount: messages.length,
    }
  })
}

export function hasExecutionData(stream: ChatRuntimeStream): boolean {
  const topology = getExecutionTopology(stream)
  return (
    topology.nodes.length > 0
    || getExecutionSteps(stream).length > 0
    || getExecutionToolCalls(stream).length > 0
    || getExecutionSubagents(stream).length > 0
    || Object.keys(asRecord(stream.values)).some((key) => key !== 'messages')
  )
}

export function summarizeExecutionStatus(stream: ChatRuntimeStream, fallback: string): string {
  const activeSubagents = stream.activeSubagents?.length ?? 0
  if (activeSubagents > 0) {
    return activeSubagents === 1
      ? '正在运行 1 个子代理…'
      : `正在运行 ${activeSubagents} 个子代理…`
  }

  const tools = getExecutionToolCalls(stream)
  const activeTools = tools.filter((item) => item.state === 'running' || item.state === 'pending')
  if (activeTools.length > 0) {
    return `正在调用工具… ${activeTools.slice(0, 3).map((item) => item.name).join(' · ')}`
  }

  const steps = getExecutionSteps(stream)
  const last = steps.at(-1)
  if (stream.isLoading && last?.node) {
    return `正在执行 ${last.node}…`
  }

  return fallback
}
