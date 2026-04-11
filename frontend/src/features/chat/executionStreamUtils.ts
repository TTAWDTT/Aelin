import type { BaseMessage } from '@langchain/core/messages'
import type { AssistantGraph } from '@langchain/langgraph-sdk'

export type ChatStreamState = {
  messages: Array<Record<string, unknown>>
  answer?: string
  todos?: unknown[]
  [key: string]: unknown
}

export type ChatRuntimeStream = {
  messages?: BaseMessage[]
  values?: ChatStreamState
  isLoading?: boolean
  subagents?: Map<string, unknown>
  getToolCalls?: (message: BaseMessage) => unknown[]
  getSubagentsByMessage?: (messageId: string) => unknown[]
  getMessagesMetadata?: (
    message: BaseMessage,
    index?: number,
  ) => {
    messageId?: string
    branch?: string
    streamMetadata?: Record<string, unknown>
  } | undefined
}

export type ExecutionGraphNode = {
  id: string
  name: string
  kind: string
  depth: number
  visits: number
  toolCalls: number
  subagents: number
  activeNamespaces: number
  status: 'idle' | 'completed' | 'running'
}

export type ExecutionGraphEdge = {
  source: string
  target: string
  conditional?: boolean
  active: boolean
  traversed: number
  namespaces: number
}

type ExecutionActivity = {
  node: string
  namespace: string
  status: string
  toolCalls: number
  subagents: number
}

export type ExecutionToolCall = {
  key: string
  name: string
  state: string
  args: string
  result: string
  filePath?: string
}

export type ExecutionTodoItem = {
  key: string
  title: string
  detail?: string
  status: 'pending' | 'completed'
}

export type ExecutionSubagent = {
  key: string
  name: string
  type: string
  status: string
  depth: number
  messageCount: number
  namespace?: string
  preview?: string
}

export type ExecutionNamespaceLane = {
  key: string
  label: string
  status: 'idle' | 'completed' | 'running'
  nodes: string[]
  currentNode?: string
  toolCalls: number
  subagents: number
}

export type ExecutionRuntime = {
  graph: {
    nodes: ExecutionGraphNode[]
    edges: ExecutionGraphEdge[]
  }
  lanes: ExecutionNamespaceLane[]
  tools: ExecutionToolCall[]
  subagents: ExecutionSubagent[]
  todos: ExecutionTodoItem[]
  live: ExecutionLiveSummary
  hasOfficialGraph: boolean
  hasExecution: boolean
}

export type ExecutionAnalysis = {
  runtime: ExecutionRuntime
  toolCallsByMessage: Map<string, ExecutionToolCall[]>
}

export type ExecutionLiveSummary = {
  currentNode?: string
  currentNamespace?: string
  runningTools: ExecutionToolCall[]
  runningToolCount: number
  recentCompletedTools: ExecutionToolCall[]
  recentCompletedToolCount: number
  runningSubagents: ExecutionSubagent[]
  runningSubagentCount: number
  recentCompletedSubagents: ExecutionSubagent[]
  recentCompletedSubagentCount: number
  todos: ExecutionTodoItem[]
  todoCount: number
}

type MessageRuntimeRow = {
  messageId: string
  node: string
  namespace: string
  status: string
  toolCalls: ExecutionToolCall[]
  subagents: ExecutionSubagent[]
  hasWork: boolean
}

const GENERIC_TOOL_NAMES = new Set(['', 'tool'])

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

function normalizeStatus(value: unknown, fallback = 'idle'): string {
  const text = String(value || '').trim().toLowerCase()
  return text || fallback
}

function isActiveStatus(value: unknown): boolean {
  const status = normalizeStatus(value)
  return status === 'running' || status === 'pending' || status === 'streaming' || status === 'preparing'
}

function isCompletedStatus(value: unknown): boolean {
  const status = normalizeStatus(value)
  return status === 'completed' || status === 'success'
}

function hasMeaningfulArgsText(value: string): boolean {
  const text = String(value || '').trim()
  return Boolean(text) && text !== '{}' && text !== '[]' && text !== 'null'
}

function isSettledToolState(state: string): boolean {
  return state === 'completed' || state === 'error' || state === 'failed'
}

function shouldDisplayToolCall(tool: ExecutionToolCall, hasStableId: boolean): boolean {
  if (hasStableId) return true
  if (tool.result) return true
  if (hasMeaningfulArgsText(tool.args)) return true
  if (isSettledToolState(tool.state)) return true
  return !GENERIC_TOOL_NAMES.has(tool.name.toLowerCase())
}

function messagePreview(message: BaseMessage): string {
  const content = (message as any)?.content
  if (typeof content === 'string') return compactText(content)
  if (Array.isArray(content)) {
    const joined = content
      .map((item) => {
        const record = asRecord(item)
        return record.type === 'text' ? String(record.text || '') : ''
      })
      .filter(Boolean)
      .join(' ')
    return compactText(joined)
  }
  return ''
}

function buildExecutionTodos(values: Record<string, unknown>): ExecutionTodoItem[] {
  const rawTodos = Array.isArray(values.todos) ? values.todos : []
  const items: ExecutionTodoItem[] = []
  rawTodos.forEach((item, index) => {
    const record = asRecord(item)
    const title = String(record.title || record.content || `Todo ${index + 1}`).trim()
    if (!title) return
    const detail = compactText(record.detail || record.description || '', 180)
    items.push({
      key: String(record.id || record.key || `todo:${index}`),
      title,
      detail: detail || undefined,
      status: Boolean(record.done) ? 'completed' : 'pending',
    })
  })
  return items
}

function createMetadataReader(stream: ChatRuntimeStream) {
  return typeof stream.getMessagesMetadata === 'function'
    ? stream.getMessagesMetadata.bind(stream)
    : (() => undefined)
}

function getMessageId(message: BaseMessage, metadataMessageId: string | undefined, index: number): string {
  const direct = String((message as any)?.id || '').trim()
  if (direct) return direct
  const meta = String(metadataMessageId || '').trim()
  if (meta) return meta
  return `message:${index}`
}

function getToolCallsForMessage(
  stream: ChatRuntimeStream,
  message: BaseMessage,
  index: number,
  messageCount: number,
): ExecutionToolCall[] {
  if (!stream.getToolCalls) return []
  const rows = (() => {
    try {
      return stream.getToolCalls?.(message) ?? []
    } catch {
      return []
    }
  })()
  const deduped = new Map<string, ExecutionToolCall & { hasStableId: boolean }>()

  const isLatestMessage = index === messageCount - 1

  rows.forEach((item, index) => {
    const record = asRecord(item)
    const call = asRecord(record.call)
    const callId = String(record.id || call.id || '').trim()
    const result = record.result
    const helperState = normalizeStatus(record.status || record.state, result == null ? 'pending' : 'completed')
    const isPendingWithoutResult = helperState === 'pending' && result == null
    const isPreparingArgs = isPendingWithoutResult && Boolean(stream.isLoading) && isLatestMessage
    const tool = {
      key: callId || `${String(call.name || record.name || 'tool').trim() || 'tool'}:${index}`,
      name: String(call.name || record.name || 'tool').trim() || 'tool',
      state: isPreparingArgs ? 'preparing' : isPendingWithoutResult ? 'running' : helperState,
      args: call.args == null ? '' : stableJson(call.args, 160),
      result: result == null ? '' : stableJson(result, 180),
      filePath: extractToolFilePath(call.args, result),
      hasStableId: Boolean(callId),
    }

    if (!shouldDisplayToolCall(tool, tool.hasStableId)) return

    const existing = deduped.get(tool.key)
    if (!existing) {
      deduped.set(tool.key, tool)
      return
    }

    const existingSettled = isSettledToolState(existing.state)
    const nextSettled = isSettledToolState(tool.state)
    if (!existingSettled && nextSettled) {
      deduped.set(tool.key, tool)
      return
    }
    if ((existing.result?.length || 0) <= (tool.result?.length || 0)) {
      deduped.set(tool.key, tool)
    }
  })

  return Array.from(deduped.values()).map(({ hasStableId: _hasStableId, ...tool }) => tool)
}

function extractToolFilePath(args: unknown, result: unknown): string | undefined {
  const argRecord = asRecord(args)
  const resultRecord = asRecord(result)
  const candidates = [
    argRecord.file_path,
    argRecord.path,
    resultRecord.file_path,
    resultRecord.path,
  ]
  for (const candidate of candidates) {
    const text = String(candidate || '').trim()
    if (!text.startsWith('/')) continue
    return text
  }
  return undefined
}

function getSubagentsForMessage(stream: ChatRuntimeStream, messageId: string): ExecutionSubagent[] {
  if (!stream.getSubagentsByMessage) return []
  const rows = (() => {
    try {
      return stream.getSubagentsByMessage?.(messageId)
    } catch {
      return []
    }
  })()
  if (!Array.isArray(rows)) return []
  return rows.map((item, index) => {
    const record = asRecord(item)
    const messages = Array.isArray(record.messages) ? record.messages : []
    return {
      key: String(record.id || record.toolCallId || `subagent:${messageId}:${index}`),
      name: String(record.name || record.subagent_type || 'subagent'),
      type: String(record.subagent_type || record.type || 'subagent'),
      status: normalizeStatus(record.status, 'idle'),
      depth: Number(record.depth || 1),
      messageCount: messages.length,
      namespace: Array.isArray(record.namespace) ? record.namespace.map(String).join(' / ') : undefined,
    }
  })
}

function getRuntimeSubagents(stream: ChatRuntimeStream): ExecutionSubagent[] {
  if (!(stream.subagents instanceof Map)) return []
  return Array.from(stream.subagents.values())
    .map((item, index) => {
      const record = asRecord(item)
      const toolCall = asRecord(record.toolCall)
      const args = asRecord(toolCall.args)
      const messages = Array.isArray(record.messages) ? record.messages : []
      const namespace = Array.isArray(record.namespace)
        ? record.namespace.map(String).join(' / ')
        : ''
      return {
        key: String(record.id || toolCall.id || `subagent:${index}`),
        name: String(args.subagent_type || record.name || 'subagent'),
        type: String(args.subagent_type || record.type || 'subagent'),
        status: normalizeStatus(record.status, 'idle'),
        depth: Number(record.depth || 0),
        messageCount: messages.length,
        namespace: namespace || undefined,
        preview: messages.length > 0 ? messagePreview(messages[messages.length - 1] as BaseMessage) : undefined,
      }
    })
    .filter((item) => Boolean(item.key))
}

function getMessageRuntimeRows(stream: ChatRuntimeStream): MessageRuntimeRow[] {
  const messages = Array.isArray(stream.messages) ? stream.messages : []
  const readMetadata = createMetadataReader(stream)

  return messages.map((message, index) => {
    const metadata = readMetadata(message, index)
    const streamMetadata = asRecord(metadata?.streamMetadata)
    const messageId = getMessageId(message, metadata?.messageId, index)
    const toolCalls = getToolCallsForMessage(stream, message, index, messages.length)
    const subagents = getSubagentsForMessage(stream, messageId)
    const node = String(streamMetadata.langgraph_node || '').trim()
    const namespace = String(
      streamMetadata.langgraph_checkpoint_ns
      || streamMetadata.checkpoint_ns
      || metadata?.branch
      || 'root',
    )
    const hasWork = Boolean(node) || toolCalls.length > 0 || subagents.length > 0

    return {
      messageId,
      node,
      namespace,
      status: Boolean(stream.isLoading) && index === messages.length - 1 ? 'running' : 'completed',
      toolCalls,
      subagents,
      hasWork,
    }
  })
}

function buildExecutionActivities(rows: MessageRuntimeRow[]): ExecutionActivity[] {
  return rows
    .filter((row) => row.hasWork && Boolean(row.node))
    .map((row) => ({
      node: row.node,
      namespace: row.namespace,
      status: row.status,
      toolCalls: row.toolCalls.length,
      subagents: row.subagents.length,
    }))
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

function buildExecutionGraph(
  assistantGraph: AssistantGraph | null | undefined,
  activities: ExecutionActivity[],
): {
  nodes: ExecutionGraphNode[]
  edges: ExecutionGraphEdge[]
} {
  const baseNodes = (Array.isArray(assistantGraph?.nodes) ? assistantGraph.nodes : [])
    .map((item) => {
      const id = String(item?.id || '').trim()
      if (!id) return null
      const data = asRecord(item?.data)
      return {
        id,
        name: String(item?.name || data.label || data.name || id),
        kind: String(data.kind || data.type || 'node'),
      }
    })
    .filter((item): item is { id: string; name: string; kind: string } => item != null)

  const rawEdges = (Array.isArray(assistantGraph?.edges) ? assistantGraph.edges : [])
    .map((edge) => ({
      source: String(edge?.source || '').trim(),
      target: String(edge?.target || '').trim(),
      conditional: Boolean(edge?.conditional),
    }))
    .filter((edge) => edge.source && edge.target)

  const depths = computeDepths(baseNodes, rawEdges)
  const nodeIds = new Set(baseNodes.map((node) => node.id))
  const turnCounts = new Map<string, number>()
  const toolCallCounts = new Map<string, number>()
  const subagentCounts = new Map<string, number>()
  const edgeTraversals = new Map<string, number>()
  const activeNamespacesByNode = new Map<string, Set<string>>()
  const traversedNamespacesByEdge = new Map<string, Set<string>>()
  const activitiesByNamespace = new Map<string, ExecutionActivity[]>()

  for (const activity of activities) {
    if (!nodeIds.has(activity.node)) continue
    turnCounts.set(activity.node, (turnCounts.get(activity.node) ?? 0) + 1)
    toolCallCounts.set(activity.node, (toolCallCounts.get(activity.node) ?? 0) + activity.toolCalls)
    subagentCounts.set(activity.node, (subagentCounts.get(activity.node) ?? 0) + activity.subagents)
    const bucket = activitiesByNamespace.get(activity.namespace) ?? []
    bucket.push(activity)
    activitiesByNamespace.set(activity.namespace, bucket)
    if (activity.status === 'running') {
      const namespaces = activeNamespacesByNode.get(activity.node) ?? new Set<string>()
      namespaces.add(activity.namespace)
      activeNamespacesByNode.set(activity.node, namespaces)
    }
  }

  for (const namespaceActivities of activitiesByNamespace.values()) {
    const nodeKeys = namespaceActivities
      .map((activity) => activity.node)
      .filter((node) => nodeIds.has(node))
    for (let index = 0; index < nodeKeys.length - 1; index += 1) {
      const source = nodeKeys[index]
      const target = nodeKeys[index + 1]
      const edgeKey = `${source}->${target}`
      edgeTraversals.set(edgeKey, (edgeTraversals.get(edgeKey) ?? 0) + 1)
      const namespaces = traversedNamespacesByEdge.get(edgeKey) ?? new Set<string>()
      namespaces.add(namespaceActivities[index]?.namespace || 'root')
      traversedNamespacesByEdge.set(edgeKey, namespaces)
    }
  }

  return {
    nodes: baseNodes.map((node) => ({
      ...node,
      depth: depths.get(node.id) ?? 0,
      visits: turnCounts.get(node.id) ?? 0,
      toolCalls: toolCallCounts.get(node.id) ?? 0,
      subagents: subagentCounts.get(node.id) ?? 0,
      activeNamespaces: activeNamespacesByNode.get(node.id)?.size ?? 0,
      status: (activeNamespacesByNode.get(node.id)?.size ?? 0) > 0
        ? 'running'
        : (turnCounts.get(node.id) ?? 0) > 0
          ? 'completed'
          : 'idle',
    })),
    edges: rawEdges.map((edge) => {
      const edgeKey = `${edge.source}->${edge.target}`
      const traversed = edgeTraversals.get(edgeKey) ?? 0
      return {
        ...edge,
        traversed,
        namespaces: traversedNamespacesByEdge.get(edgeKey)?.size ?? 0,
        active:
          traversed > 0
          || (activeNamespacesByNode.get(edge.source)?.size ?? 0) > 0
          || (activeNamespacesByNode.get(edge.target)?.size ?? 0) > 0,
      }
    }),
  }
}

function buildExecutionLanes(activities: ExecutionActivity[]): ExecutionNamespaceLane[] {
  const byNamespace = new Map<string, ExecutionActivity[]>()
  for (const activity of activities) {
    const bucket = byNamespace.get(activity.namespace) ?? []
    bucket.push(activity)
    byNamespace.set(activity.namespace, bucket)
  }
  return Array.from(byNamespace.entries())
    .map(([namespace, items]) => {
      const status: ExecutionNamespaceLane['status'] = items.some((item) => item.status === 'running')
        ? 'running'
        : items.length > 0
          ? 'completed'
          : 'idle'
      return {
        key: namespace,
        label: namespace === 'root' ? 'root' : namespace,
        status,
        nodes: Array.from(new Set(items.map((item) => item.node).filter(Boolean))),
        currentNode: items[items.length - 1]?.node,
        toolCalls: items.reduce((sum, item) => sum + item.toolCalls, 0),
        subagents: items.reduce((sum, item) => sum + item.subagents, 0),
      }
    })
    .sort((left, right) => {
      if (left.status === right.status) return left.label.localeCompare(right.label)
      if (left.status === 'running') return -1
      if (right.status === 'running') return 1
      return left.label.localeCompare(right.label)
    })
}

function dedupeToolCalls(tools: ExecutionToolCall[]): ExecutionToolCall[] {
  const map = new Map<string, ExecutionToolCall>()
  tools.forEach((tool) => {
    map.set(tool.key, tool)
  })
  return Array.from(map.values())
}

function buildExecutionLiveSummary(
  lanes: ExecutionNamespaceLane[],
  tools: ExecutionToolCall[],
  subagents: ExecutionSubagent[],
  todos: ExecutionTodoItem[],
): ExecutionLiveSummary {
  const runningLane = lanes.find((item) => item.status === 'running')
  const allRunningTools = tools.filter((tool) => isActiveStatus(tool.state))
  const allRecentCompletedTools = tools
    .filter((tool) => isCompletedStatus(tool.state))
    .slice(-2)
    .reverse()
  const allRunningSubagents = subagents.filter((item) => isActiveStatus(item.status))
  const allRecentCompletedSubagents = subagents
    .filter((item) => isCompletedStatus(item.status))
    .slice(-2)
    .reverse()

  return {
    currentNode: runningLane?.currentNode,
    currentNamespace: runningLane?.key,
    runningTools: allRunningTools.slice(0, 3),
    runningToolCount: allRunningTools.length,
    recentCompletedTools: allRecentCompletedTools,
    recentCompletedToolCount: allRecentCompletedTools.length,
    runningSubagents: allRunningSubagents.slice(0, 2),
    runningSubagentCount: allRunningSubagents.length,
    recentCompletedSubagents: allRecentCompletedSubagents,
    recentCompletedSubagentCount: allRecentCompletedSubagents.length,
    todos: todos.slice(0, 5),
    todoCount: todos.length,
  }
}

export function getMessageToolCallMap(stream: ChatRuntimeStream): Map<string, ExecutionToolCall[]> {
  const entries = getMessageRuntimeRows(stream)
    .filter((row) => row.toolCalls.length > 0)
    .map((row) => [row.messageId, row.toolCalls] as const)
  return new Map(entries)
}

export function analyzeExecutionStream(
  stream: ChatRuntimeStream,
  assistantGraph?: AssistantGraph | null,
): ExecutionAnalysis {
  const rows = getMessageRuntimeRows(stream)
  const activities = buildExecutionActivities(rows)
  const lanes = buildExecutionLanes(activities)
  const graph = buildExecutionGraph(assistantGraph, activities)
  const subagents = getRuntimeSubagents(stream)
  const values = asRecord(stream.values)
  const todos = buildExecutionTodos(values)
  const tools = dedupeToolCalls(rows.flatMap((row) => row.toolCalls))
  const live = buildExecutionLiveSummary(lanes, tools, subagents, todos)
  const hasOfficialGraph = graph.nodes.length > 0 || graph.edges.length > 0
  const hasExecution =
    hasOfficialGraph
    || tools.length > 0
    || subagents.length > 0
    || todos.length > 0
    || lanes.length > 0
    || Object.keys(values).some((key) => key !== 'messages')

  return {
    runtime: {
      graph,
      lanes,
      tools,
      subagents,
      todos,
      live,
      hasOfficialGraph,
      hasExecution,
    },
    toolCallsByMessage: new Map(
      rows
        .filter((row) => row.toolCalls.length > 0)
        .map((row) => [row.messageId, row.toolCalls] as const),
    ),
  }
}

export function getExecutionRuntime(
  stream: ChatRuntimeStream,
  assistantGraph?: AssistantGraph | null,
): ExecutionRuntime {
  return analyzeExecutionStream(stream, assistantGraph).runtime
}

export function summarizeExecutionStatus(
  runtime: ExecutionRuntime,
  options: {
    isLoading: boolean
    fallback: string
  },
): string {
  const runningSubagents = runtime.live.runningSubagents.length
  if (runningSubagents > 0) {
    return runningSubagents === 1
      ? '正在运行 1 个子代理…'
      : `正在运行 ${runningSubagents} 个子代理…`
  }

  const activeTools = runtime.live.runningTools
  if (activeTools.length > 0) {
    return `正在调用工具… ${activeTools.slice(0, 3).map((item) => item.name).join(' · ')}`
  }

  if (options.isLoading && runtime.live.currentNode) {
    return `正在执行 ${runtime.live.currentNode}…`
  }

  if (!options.isLoading && runtime.live.recentCompletedTools.length > 0) {
    return `已完成 ${runtime.live.recentCompletedTools.map((item) => item.name).join(' · ')}`
  }

  return options.fallback
}
