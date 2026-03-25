import type {
  DeepAgentsTopology,
  DeepAgentsRunState,
  DeepAgentsStreamPart,
} from '@/shared/api/types'

export type RunTaskKind = 'tool' | 'model' | 'middleware' | 'task'
export type RunGraphNodeKind = 'start' | 'tool' | 'model' | 'middleware' | 'final' | 'error'
export type RunGraphEdgeKind = 'flow' | 'branch'

export interface RunTaskSnapshot {
  key: string
  id: string
  rawName: string
  name: string
  kind: RunTaskKind
  status: string
  summary: string
  ns: string[]
  updates: number
  lastTs: number
  error?: string
  toolName?: string
}

export interface RunGraphNode {
  key: string
  kind: RunGraphNodeKind
  title: string
  summary: string
  status: string
  ts: number
  clusterKey: string
  depth: number
  toolName?: string
  provider?: string
}

export interface RunGraphEdge {
  key: string
  from: string
  to: string
  kind: RunGraphEdgeKind
  status: string
}

export interface RunGraphCluster {
  key: string
  label: string
  pathLabel: string
  ns: string[]
  parentKey?: string
  depth: number
  status: string
  startTs: number
  lastTs: number
  nodeKeys: string[]
  anchorNodeKey?: string
}

export interface RunGraphModel {
  nodes: RunGraphNode[]
  edges: RunGraphEdge[]
  clusters: RunGraphCluster[]
  rootClusterKey: string
  activeNodeKey?: string
  latestNodeKey?: string
  activeClusterKey?: string
}

export interface ExecutionToolCall {
  key: string
  name: string
  status: string
  summary: string
  provider: string
  latencyMs: number
  isWrite: boolean
}

const ROOT_CLUSTER_KEY = 'cluster:root'

function compactText(value: unknown, max = 180): string {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function stableStringify(value: unknown): string {
  try {
    return JSON.stringify(value)
  } catch {
    return String(value ?? '')
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function summarizeScalar(value: unknown, max = 220): unknown {
  if (typeof value === 'string') return compactText(value, max)
  if (typeof value === 'number' || typeof value === 'boolean' || value == null) return value
  return undefined
}

function summarizeUnknown(value: unknown, depth = 0): unknown {
  const scalar = summarizeScalar(value)
  if (scalar !== undefined) return scalar
  if (depth >= 2) {
    if (Array.isArray(value)) return `items=${value.length}`
    return `keys=${Object.keys(asRecord(value)).length}`
  }
  if (Array.isArray(value)) {
    return value.slice(0, 4).map((item) => summarizeUnknown(item, depth + 1))
  }
  const record = asRecord(value)
  const out: Record<string, unknown> = {}
  for (const key of Object.keys(record).slice(0, 8)) {
    out[key] = summarizeUnknown(record[key], depth + 1)
  }
  if (Object.keys(record).length > 8) out.__truncated = true
  return out
}

function humanizeTaskName(value: unknown): string {
  const raw = String(value ?? '').trim()
  if (!raw) return 'Task'
  if (raw === 'model') return 'Model'
  if (raw === 'tools') return 'Tool runtime'
  if (raw.endsWith('.before_agent')) {
    return raw
      .replace(/Middleware\.before_agent$/, '')
      .replace(/_/g, ' ')
      .trim() || 'Runtime prep'
  }
  if (raw.endsWith('.after_model')) {
    return raw
      .replace(/Middleware\.after_model$/, '')
      .replace(/_/g, ' ')
      .trim() || 'Post-process'
  }
  return raw.replace(/_/g, ' ')
}

function humanizeNamespaceSegment(value: string): string {
  const clean = String(value || '')
    .replace(/^__pregel.*$/, '')
    .replace(/^subgraph:/i, '')
    .replace(/^subagent:/i, '')
    .replace(/[_-]+/g, ' ')
    .trim()
  if (!clean) return 'Branch'
  return clean
}

function classifyTaskRecord(data: Record<string, unknown>): RunTaskKind {
  const toolName = String(data.tool_name ?? '').trim()
  if (toolName) return 'tool'
  const name = String(data.name ?? '').trim().toLowerCase()
  if (name === 'model') return 'model'
  if (name.includes('middleware')) return 'middleware'
  return 'task'
}

function normalizePartPayload(event: string, payload: Record<string, unknown>): Record<string, unknown> {
  const ns = Array.isArray(payload.ns) ? payload.ns.map((item) => String(item)) : undefined
  const data = payload.data
  const base: Record<string, unknown> = {
    type: payload.type ?? event,
  }
  if (typeof payload.run_id === 'string' && payload.run_id) base.run_id = payload.run_id
  if (typeof payload.seq === 'number') base.seq = payload.seq
  if (ns?.length) base.ns = ns

  if (event === 'messages') {
    const dataRecord = asRecord(data)
    base.data = {
      content: compactText(dataRecord.content, 800),
      metadata: summarizeUnknown(dataRecord.metadata),
    }
    return base
  }

  if (event === 'topology') {
    const dataRecord = asRecord(data)
    const nodes = Array.isArray(dataRecord.nodes) ? dataRecord.nodes : []
    const edges = Array.isArray(dataRecord.edges) ? dataRecord.edges : []
    base.data = {
      nodes: nodes
        .slice(0, 64)
        .map((item) => {
          const record = asRecord(item)
          return {
            id: compactText(record.id, 80),
            name: compactText(record.name, 80),
            kind: compactText(record.kind, 40),
          }
        }),
      edges: edges
        .slice(0, 128)
        .map((item) => {
          const record = asRecord(item)
          return {
            source: compactText(record.source, 80),
            target: compactText(record.target, 80),
            conditional: Boolean(record.conditional),
          }
        }),
      mermaid: compactText(dataRecord.mermaid, 4000),
    }
    return base
  }

  if (event === 'tasks') {
    const dataRecord = asRecord(data)
    base.data = {
      id: dataRecord.id,
      name: dataRecord.name,
      status: dataRecord.status,
      tool_name: dataRecord.tool_name,
      tool_call: summarizeUnknown(dataRecord.tool_call),
      tool_calls: summarizeUnknown(dataRecord.tool_calls),
      result_summary: summarizeScalar(dataRecord.result_summary, 220),
      interrupts: Array.isArray(dataRecord.interrupts) ? dataRecord.interrupts.length : 0,
      triggers: Array.isArray(dataRecord.triggers) ? dataRecord.triggers.length : 0,
      error: summarizeScalar(dataRecord.error, 160),
    }
    return base
  }

  if (event === 'values') {
    const dataRecord = asRecord(data)
    const todos = Array.isArray(dataRecord.todos) ? dataRecord.todos : []
    const messages = Array.isArray(dataRecord.messages) ? dataRecord.messages : []
    base.data = {
      answer: compactText(dataRecord.answer, 800),
      todos: todos.slice(0, 6).map((item) => summarizeUnknown(item, 1)),
      todos_count: todos.length,
      messages_count: messages.length,
      plan: summarizeUnknown(dataRecord.plan),
    }
    return base
  }

  if (event === 'updates') {
    const summary = summarizeUnknown(data)
    base.data = typeof summary === 'object' && summary != null ? summary : { summary }
    return base
  }

  if (event === 'final') {
    const dataRecord = asRecord(data)
    base.data = {
      answer: compactText(dataRecord.answer, 800),
      finished_at: dataRecord.finished_at,
      usage: summarizeUnknown(dataRecord.usage),
    }
    return base
  }

  if (event === 'error') {
    const dataRecord = asRecord(data)
    base.data = {
      message: compactText(dataRecord.message, 300),
      code: dataRecord.code,
    }
    return base
  }

  if (event === 'start') {
    const dataRecord = asRecord(data)
    base.data = {
      query: compactText(dataRecord.query, 300),
      workspace: dataRecord.workspace,
      source: dataRecord.source,
    }
    return base
  }

  base.data = summarizeUnknown(data)
  return base
}

function streamPartId(event: string, payload: Record<string, unknown>, ts: number): string {
  const nsRaw = Array.isArray(payload.ns) ? payload.ns.join('/') : ''
  return `${event}:${nsRaw}:${ts}:${Math.random().toString(36).slice(2, 8)}`
}

function normalizeNs(ns: string[] | undefined): string[] {
  return (ns ?? [])
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .filter((item) => !item.startsWith('__pregel'))
}

function formatNsLabel(ns: string[] | undefined): string {
  const clean = normalizeNs(ns)
  return clean.length ? clean.join(' / ') : 'root'
}

function clusterKeyFromNs(ns: string[]): string {
  return ns.length ? `cluster:${ns.join('/')}` : ROOT_CLUSTER_KEY
}

function mergeStatuses(current: string, next: string): string {
  const rank = (value: string): number => {
    const lowered = String(value || '').toLowerCase()
    if (lowered === 'failed' || lowered === 'error') return 4
    if (lowered === 'running' || lowered === 'pending') return 3
    if (lowered === 'completed' || lowered === 'success') return 2
    if (lowered) return 1
    return 0
  }
  return rank(next) >= rank(current) ? (next || current) : current
}

function inferProvider(name: string): string {
  const lowered = String(name || '').toLowerCase()
  if (lowered.startsWith('gws') || lowered.startsWith('google') || lowered.startsWith('gmail')) return 'google'
  if (lowered.startsWith('device') || lowered.startsWith('screen')) return 'device'
  if (lowered.startsWith('web')) return 'web'
  return 'core'
}

function coerceTaskName(data: Record<string, unknown>): string {
  const toolName = compactText(data.tool_name, 80)
  if (toolName) return `Tool · ${toolName}`
  return humanizeTaskName(data.name ?? data.id ?? 'Task')
}

function summarizeTaskData(data: Record<string, unknown>): string {
  const rawId = compactText(data.id, 40)
  const toolCall = asRecord(data.tool_call)
  const toolArgs = compactText(stableStringify(toolCall.args), 180)
  return [
    compactText(data.status, 40),
    compactText(data.result_summary, 180),
    toolArgs ? `args=${toolArgs}` : '',
    rawId ? `id=${rawId}` : '',
    Number(data.interrupts || 0) > 0 ? `interrupts=${Number(data.interrupts)}` : '',
    Number(data.triggers || 0) > 0 ? `triggers=${Number(data.triggers)}` : '',
  ].filter(Boolean).join(' · ')
}

export function createStreamPart(event: string, payload: unknown): DeepAgentsStreamPart | null {
  const record = asRecord(payload)
  if (!event || !Object.keys(record).length) return null
  const normalized = normalizePartPayload(event, record)
  const ts = Date.now()
  const ns = Array.isArray(normalized.ns) ? normalized.ns.map((item) => String(item)) : undefined
  return {
    id: streamPartId(event, normalized, ts),
    event,
    ts,
    runId: typeof normalized.run_id === 'string' ? normalized.run_id : undefined,
    seq: typeof normalized.seq === 'number' ? normalized.seq : undefined,
    ns,
    payload: normalized,
    data: normalized.data,
  }
}

export function appendRunStatePart(
  current: DeepAgentsRunState | undefined,
  part: DeepAgentsStreamPart,
): DeepAgentsRunState {
  const next: DeepAgentsRunState = {
    parts: [...(current?.parts ?? []), part],
    runId: current?.runId ?? part.runId,
    latestValues: current?.latestValues,
    final: current?.final,
    topology: current?.topology,
  }
  if (part.event === 'topology') {
    const topology = asTopology(part.data)
    if (topology) next.topology = topology
  }
  if (part.event === 'values') {
    const values = asRecord(part.data)
    if (Object.keys(values).length) next.latestValues = values
  }
  if (part.event === 'final') {
    const final = asRecord(part.data ?? part.payload)
    if (Object.keys(final).length) next.final = final
  }
  return next
}

function asTopology(value: unknown): DeepAgentsTopology | undefined {
  const record = asRecord(value)
  const nodes = Array.isArray(record.nodes)
    ? record.nodes
      .map((item) => {
        const node = asRecord(item)
        const id = compactText(node.id, 120)
        const name = compactText(node.name, 120)
        if (!id || !name) return null
        return {
          id,
          name,
          kind: compactText(node.kind, 40) || 'node',
        }
      })
      .filter((item): item is DeepAgentsTopology['nodes'][number] => item != null)
    : []
  const edges: DeepAgentsTopology['edges'] = []
  if (Array.isArray(record.edges)) {
    for (const item of record.edges) {
      const edge = asRecord(item)
      const source = compactText(edge.source, 120)
      const target = compactText(edge.target, 120)
      if (!source || !target) continue
      edges.push({
        source,
        target,
        conditional: Boolean(edge.conditional),
      })
    }
  }
  if (!nodes.length) return undefined
  return {
    nodes,
    edges,
    mermaid: compactText(record.mermaid, 4000) || undefined,
  }
}

export function taskSnapshotsFromRunState(
  runState: DeepAgentsRunState | undefined,
): RunTaskSnapshot[] {
  const byKey = new Map<string, RunTaskSnapshot>()

  for (const part of runState?.parts ?? []) {
    if (part.event !== 'tasks') continue
    const data = asRecord(part.data)
    const ns = normalizeNs(part.ns)
    const rawId = compactText(data.id, 80) || ''
    const rawName = compactText(data.name, 120) || ''
    const name = coerceTaskName(data)
    const kind = classifyTaskRecord(data)
    const key = `${formatNsLabel(ns)}::${rawId || name}`
    const existing = byKey.get(key)
    byKey.set(key, {
      key,
      id: rawId || name,
      rawName,
      name,
      kind,
      status: compactText(data.status, 40) || existing?.status || 'unknown',
      summary: summarizeTaskData(data),
      ns,
      updates: (existing?.updates ?? 0) + 1,
      lastTs: part.ts,
      error: compactText(data.error, 160) || existing?.error,
      toolName: compactText(data.tool_name, 80) || existing?.toolName,
    })
  }

  return [...byKey.values()].sort((a, b) => a.lastTs - b.lastTs)
}

function buildGraphNodeFromTask(task: RunTaskSnapshot): RunGraphNode {
  const clusterKey = clusterKeyFromNs(task.ns)
  const depth = task.ns.length
  return {
    key: `node:${task.key}`,
    kind: task.kind === 'tool'
      ? 'tool'
      : task.kind === 'model'
        ? 'model'
        : task.kind === 'middleware'
          ? 'middleware'
          : 'model',
    title: task.name,
    summary: task.summary,
    status: task.status || 'unknown',
    ts: task.lastTs,
    clusterKey,
    depth,
    toolName: task.toolName,
    provider: inferProvider(task.toolName || task.name),
  }
}

function kindFromTopologyNode(node: DeepAgentsTopology['nodes'][number]): RunGraphNodeKind {
  const id = String(node.id || '').trim().toLowerCase()
  const name = String(node.name || '').trim().toLowerCase()
  if (id === '__start__') return 'start'
  if (id === '__end__') return 'final'
  if (name === 'tools') return 'tool'
  if (name === 'model') return 'model'
  if (name.includes('middleware')) return 'middleware'
  return 'model'
}

function titleFromTopologyNode(node: DeepAgentsTopology['nodes'][number]): string {
  const id = String(node.id || '').trim()
  if (id === '__start__') return 'Run started'
  if (id === '__end__') return 'Final answer'
  return humanizeTaskName(node.name)
}

function computeTopologyDepths(topology: DeepAgentsTopology): Map<string, number> {
  const incoming = new Map<string, number>()
  const adjacency = new Map<string, string[]>()
  for (const node of topology.nodes) {
    incoming.set(node.id, 0)
    adjacency.set(node.id, [])
  }
  for (const edge of topology.edges) {
    adjacency.set(edge.source, [...(adjacency.get(edge.source) ?? []), edge.target])
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
  }
  const queue = topology.nodes
    .filter((node) => (incoming.get(node.id) ?? 0) === 0)
    .map((node) => node.id)
  const depths = new Map<string, number>()
  for (const nodeId of queue) depths.set(nodeId, 0)
  while (queue.length) {
    const nodeId = queue.shift() as string
    const nextDepth = (depths.get(nodeId) ?? 0) + 1
    for (const target of adjacency.get(nodeId) ?? []) {
      depths.set(target, Math.max(depths.get(target) ?? 0, nextDepth))
      incoming.set(target, (incoming.get(target) ?? 1) - 1)
      if ((incoming.get(target) ?? 0) === 0) queue.push(target)
    }
  }
  return depths
}

function createRootCluster(): RunGraphCluster {
  return {
    key: ROOT_CLUSTER_KEY,
    label: 'Main run',
    pathLabel: 'root',
    ns: [],
    depth: 0,
    status: 'ready',
    startTs: 0,
    lastTs: 0,
    nodeKeys: [],
  }
}

export function buildGraphModelFromRunState(
  runState: DeepAgentsRunState | undefined,
): RunGraphModel {
  const nodes: RunGraphNode[] = []
  const edges: RunGraphEdge[] = []
  const clusters = new Map<string, RunGraphCluster>()
  const nodeMap = new Map<string, RunGraphNode>()
  const parts = runState?.parts ?? []
  const taskSnapshots = taskSnapshotsFromRunState(runState)
  const topology = runState?.topology
  const taskByRawName = new Map<string, RunTaskSnapshot[]>()
  for (const task of taskSnapshots) {
    const rawName = String(task.rawName || '').trim()
    if (!rawName) continue
    taskByRawName.set(rawName, [...(taskByRawName.get(rawName) ?? []), task])
  }

  clusters.set(ROOT_CLUSTER_KEY, createRootCluster())

  const ensureCluster = (ns: string[]) => {
    if (!ns.length) return ROOT_CLUSTER_KEY
    for (let depth = 1; depth <= ns.length; depth += 1) {
      const path = ns.slice(0, depth)
      const key = clusterKeyFromNs(path)
      if (clusters.has(key)) continue
      const parentPath = path.slice(0, -1)
      clusters.set(key, {
        key,
        label: humanizeNamespaceSegment(path[path.length - 1]),
        pathLabel: formatNsLabel(path),
        ns: path,
        parentKey: parentPath.length ? clusterKeyFromNs(parentPath) : ROOT_CLUSTER_KEY,
        depth: path.length,
        status: 'ready',
        startTs: 0,
        lastTs: 0,
        nodeKeys: [],
      })
    }
    return clusterKeyFromNs(ns)
  }

  const attachNodeToCluster = (clusterKey: string, node: RunGraphNode) => {
    const cluster = clusters.get(clusterKey)
    if (!cluster) return
    cluster.nodeKeys.push(node.key)
    cluster.startTs = cluster.startTs === 0 ? node.ts : Math.min(cluster.startTs, node.ts)
    cluster.lastTs = Math.max(cluster.lastTs, node.ts)
    cluster.status = mergeStatuses(cluster.status, node.status)
  }

  const pushNode = (node: RunGraphNode) => {
    nodes.push(node)
    nodeMap.set(node.key, node)
    attachNodeToCluster(node.clusterKey, node)
  }

  const startPart = parts.find((part) => part.event === 'start')
  const finalPart = [...parts].reverse().find((part) => part.event === 'final')
  const errorPart = [...parts].reverse().find((part) => part.event === 'error')

  if (topology?.nodes.length) {
    const depths = computeTopologyDepths(topology)
    for (const topoNode of topology.nodes) {
      const rawName = String(topoNode.name || '').trim()
      const matchingTasks = taskByRawName.get(rawName) ?? []
      const latestTask = matchingTasks.at(-1)
      const status =
        topoNode.id === '__start__'
          ? 'completed'
          : topoNode.id === '__end__'
            ? (errorPart ? 'failed' : finalPart ? 'completed' : 'pending')
            : latestTask?.status || 'pending'
      const summary =
        topoNode.id === '__start__'
          ? compactText(asRecord(startPart?.data).query, 140)
          : topoNode.id === '__end__'
            ? compactText(asRecord((errorPart ?? finalPart)?.data).answer ?? asRecord(errorPart?.data).message, 180)
            : latestTask?.summary || ''
      const ts =
        topoNode.id === '__start__'
          ? startPart?.ts ?? 0
          : topoNode.id === '__end__'
            ? (errorPart ?? finalPart)?.ts ?? (latestTask?.lastTs ?? 0)
            : latestTask?.lastTs ?? 0
      pushNode({
        key: `topology:${topoNode.id}`,
        kind: topoNode.id === '__end__' && errorPart ? 'error' : kindFromTopologyNode(topoNode),
        title: titleFromTopologyNode(topoNode),
        summary,
        status,
        ts,
        clusterKey: ROOT_CLUSTER_KEY,
        depth: depths.get(topoNode.id) ?? 0,
        toolName: latestTask?.toolName,
        provider: inferProvider(latestTask?.toolName || topoNode.name),
      })
    }

    for (const edge of topology.edges) {
      edges.push({
        key: `topology-edge:${edge.source}:${edge.target}`,
        from: `topology:${edge.source}`,
        to: `topology:${edge.target}`,
        kind: edge.conditional ? 'branch' : 'flow',
        status: 'ready',
      })
    }
  } else {
    if (startPart) {
      pushNode({
        key: `start:${startPart.id}`,
        kind: 'start',
        title: 'Run started',
        summary: compactText(asRecord(startPart.data).query, 140),
        status: 'completed',
        ts: startPart.ts,
        clusterKey: ROOT_CLUSTER_KEY,
        depth: 0,
        provider: 'core',
      })
    }

    for (const task of taskSnapshots.filter((task) => task.ns.length === 0)) {
      pushNode({
        ...buildGraphNodeFromTask(task),
        clusterKey: ROOT_CLUSTER_KEY,
      })
    }

    if (errorPart) {
      const data = asRecord(errorPart.data)
      pushNode({
        key: `error:${errorPart.id}`,
        kind: 'error',
        title: 'Run error',
        summary: compactText(data.message, 160),
        status: 'failed',
        ts: errorPart.ts,
        clusterKey: ROOT_CLUSTER_KEY,
        depth: 0,
        provider: 'core',
      })
    } else if (finalPart) {
      const data = asRecord(finalPart.data)
      pushNode({
        key: `final:${finalPart.id}`,
        kind: 'final',
        title: 'Final answer',
        summary: compactText(data.answer, 180),
        status: 'completed',
        ts: finalPart.ts,
        clusterKey: ROOT_CLUSTER_KEY,
        depth: 0,
        provider: 'core',
      })
    }
  }

  for (const task of taskSnapshots.filter((task) => task.ns.length > 0)) {
    const clusterKey = ensureCluster(task.ns)
    pushNode({
      ...buildGraphNodeFromTask(task),
      clusterKey,
    })
  }

  const sortedClusters = [...clusters.values()].sort((a, b) => {
    if (a.depth !== b.depth) return a.depth - b.depth
    return a.startTs - b.startTs
  })

  for (const cluster of sortedClusters) {
    if (cluster.key === ROOT_CLUSTER_KEY && topology?.edges.length) continue
    const clusterNodes = cluster.nodeKeys
      .map((key) => nodeMap.get(key))
      .filter((node): node is RunGraphNode => node != null)
      .sort((a, b) => a.ts - b.ts)
    cluster.nodeKeys = clusterNodes.map((node) => node.key)
    cluster.status = clusterNodes.reduce((status, node) => mergeStatuses(status, node.status), cluster.status)

    for (let index = 0; index < clusterNodes.length - 1; index += 1) {
      const from = clusterNodes[index]
      const to = clusterNodes[index + 1]
      edges.push({
        key: `edge:${from.key}:${to.key}`,
        from: from.key,
        to: to.key,
        kind: 'flow',
        status: mergeStatuses(from.status, to.status),
      })
    }
  }

  for (const cluster of sortedClusters) {
    if (cluster.key === ROOT_CLUSTER_KEY || cluster.nodeKeys.length === 0) continue
    const firstNode = nodeMap.get(cluster.nodeKeys[0])
    const parentCluster = clusters.get(cluster.parentKey || ROOT_CLUSTER_KEY)
    const parentNodes = (parentCluster?.nodeKeys ?? [])
      .map((key) => nodeMap.get(key))
      .filter((node): node is RunGraphNode => node != null)
      .sort((a, b) => a.ts - b.ts)

    const anchor =
      [...parentNodes].reverse().find((node) => node.ts <= (firstNode?.ts ?? Number.MAX_SAFE_INTEGER))
      ?? parentNodes.at(-1)

    if (firstNode && anchor) {
      cluster.anchorNodeKey = anchor.key
      edges.push({
        key: `branch:${cluster.key}:${anchor.key}:${firstNode.key}`,
        from: anchor.key,
        to: firstNode.key,
        kind: 'branch',
        status: mergeStatuses(anchor.status, firstNode.status),
      })
    }
  }

  const activeNode = [...nodes]
    .sort((a, b) => a.ts - b.ts)
    .reverse()
    .find((node) => {
      const lowered = String(node.status || '').toLowerCase()
      return lowered === 'running' || lowered === 'pending'
    })
  const latestNode = [...nodes].sort((a, b) => a.ts - b.ts).at(-1)

  return {
    nodes: [...nodes].sort((a, b) => a.ts - b.ts),
    edges: [...edges].sort((a, b) => {
      const fromA = nodeMap.get(a.from)?.ts ?? 0
      const fromB = nodeMap.get(b.from)?.ts ?? 0
      return fromA - fromB
    }),
    clusters: sortedClusters.filter((cluster) => cluster.nodeKeys.length > 0),
    rootClusterKey: ROOT_CLUSTER_KEY,
    activeNodeKey: activeNode?.key,
    latestNodeKey: latestNode?.key,
    activeClusterKey: activeNode?.clusterKey,
  }
}

export function toolCallsFromRunState(
  runState: DeepAgentsRunState | undefined,
): ExecutionToolCall[] {
  return taskSnapshotsFromRunState(runState)
    .filter((task) => task.kind === 'tool')
    .map((task, index) => ({
      key: `${task.key}-${index}`,
      name: task.name.replace(/^Tool\s*·\s*/i, '') || task.name,
      status: String(task.status || 'unknown'),
      summary: String(task.summary || ''),
      provider: inferProvider(task.toolName || task.name),
      latencyMs: 0,
      isWrite: false,
    }))
}

export function summarizeStreamPartStatus(part: DeepAgentsStreamPart): string {
  if (part.event === 'tasks') {
    const data = asRecord(part.data)
    const name = coerceTaskName(data)
    const status = compactText(data.status, 40)
    return [name, status && status !== 'completed' ? status : ''].filter(Boolean).join(' · ')
  }
  if (part.event === 'error') {
    return compactText(asRecord(part.data).message, 220) || 'Run error'
  }
  if (part.event === 'final') {
    return 'Final answer ready'
  }
  if (part.event === 'start') {
    return 'Run started'
  }
  return ''
}

export function summarizeRunStateStatus(
  runState: DeepAgentsRunState | undefined,
  isStreaming: boolean,
): string {
  const lastTask = taskSnapshotsFromRunState(runState).at(-1)
  if (lastTask) {
    if (isStreaming) {
      const status = String(lastTask.status || '').toLowerCase()
      return [lastTask.name, status && status !== 'completed' ? lastTask.status : ''].filter(Boolean).join(' · ')
    }
    return lastTask.summary || lastTask.name
  }

  const last = [...(runState?.parts ?? [])]
    .reverse()
    .find((part) => part.event === 'error' || part.event === 'final' || part.event === 'start')

  if (!last) return isStreaming ? 'Generating' : ''
  return summarizeStreamPartStatus(last)
}
