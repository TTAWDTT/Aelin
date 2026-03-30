import type { ExecutionToolArtifact, ExecutionToolCall } from './executionStreamUtils'

type UnknownRecord = Record<string, unknown>

export type ArtifactPreviewKind =
  | 'markdown'
  | 'html'
  | 'svg'
  | 'json'
  | 'text'
  | 'image-data-url'
  | 'pdf-data-url'
  | 'unknown'

export interface ChatArtifact {
  path: string
  name: string
  extension: string
  mimeType: string
  sizeBytes: number
  content: string
  downloadBase64?: string
  createdAt?: string
  modifiedAt?: string
  previewKind: ArtifactPreviewKind
  previewable: boolean
}

function artifactTimestamp(value?: string): number {
  if (!value) return 0
  const time = Date.parse(value)
  return Number.isFinite(time) ? time : 0
}

const FILE_OUTPUT_TOOL_NAMES = new Set([
  'write_file',
  'edit_file',
  'move_file',
])

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as UnknownRecord
    : {}
}

function contentToString(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map((item) => String(item ?? '')).join('\n')
  return ''
}

function normalizePreviewKind(value: unknown): ArtifactPreviewKind | null {
  const text = String(value || '').trim().toLowerCase()
  if (
    text === 'markdown'
    || text === 'html'
    || text === 'svg'
    || text === 'json'
    || text === 'text'
    || text === 'image-data-url'
    || text === 'pdf-data-url'
    || text === 'unknown'
  ) {
    return text
  }
  return null
}

function fileNameFromPath(path: string): string {
  const normalized = String(path || '').trim()
  if (!normalized) return 'file'
  const segments = normalized.split('/').filter(Boolean)
  return segments.at(-1) || normalized
}

function extensionFromPath(path: string): string {
  const name = fileNameFromPath(path)
  const match = /\.([a-z0-9_-]+)$/i.exec(name)
  return match ? match[1].toLowerCase() : ''
}

function inferMimeType(path: string, content: string): string {
  const extension = extensionFromPath(path)
  if (content.startsWith('data:image/')) {
    const match = /^data:(image\/[a-z0-9.+-]+);/i.exec(content)
    return match?.[1] || 'image/*'
  }
  if (content.startsWith('data:application/pdf')) return 'application/pdf'
  switch (extension) {
    case 'md':
    case 'markdown':
      return 'text/markdown'
    case 'html':
    case 'htm':
      return 'text/html'
    case 'svg':
      return 'image/svg+xml'
    case 'json':
      return 'application/json'
    case 'csv':
      return 'text/csv'
    case 'txt':
    case 'log':
      return 'text/plain'
    case 'js':
      return 'text/javascript'
    case 'ts':
      return 'text/typescript'
    case 'jsx':
      return 'text/jsx'
    case 'tsx':
      return 'text/tsx'
    case 'css':
      return 'text/css'
    case 'xml':
      return 'application/xml'
    case 'yml':
    case 'yaml':
      return 'application/yaml'
    case 'pdf':
      return 'application/pdf'
    case 'png':
      return 'image/png'
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg'
    case 'gif':
      return 'image/gif'
    case 'webp':
      return 'image/webp'
    default:
      return 'text/plain'
  }
}

function inferPreviewKind(path: string, mimeType: string, content: string): ArtifactPreviewKind {
  const extension = extensionFromPath(path)
  if (content.startsWith('data:image/')) return 'image-data-url'
  if (content.startsWith('data:application/pdf')) return 'pdf-data-url'
  if (mimeType === 'text/markdown') return 'markdown'
  if (mimeType === 'text/html') return 'html'
  if (mimeType === 'image/svg+xml') return 'svg'
  if (mimeType === 'application/json') return 'json'
  if (
    mimeType.startsWith('text/')
    || ['js', 'ts', 'jsx', 'tsx', 'css', 'xml', 'yml', 'yaml'].includes(extension)
  ) {
    return 'text'
  }
  return content.trim() ? 'text' : 'unknown'
}

function estimateBase64Size(base64: string): number {
  const clean = String(base64 || '').trim().replace(/\s+/g, '')
  if (!clean) return 0
  const padding = clean.endsWith('==') ? 2 : clean.endsWith('=') ? 1 : 0
  return Math.max(0, Math.floor((clean.length * 3) / 4) - padding)
}

function artifactFromStateEntry(path: string, value: unknown): ChatArtifact | null {
  const record = asRecord(value)
  const content = contentToString(record.content)
  if (!content && !record.created_at && !record.modified_at) return null
  const mimeType = inferMimeType(path, content)
  const previewKind = inferPreviewKind(path, mimeType, content)
  return {
    path,
    name: fileNameFromPath(path),
    extension: extensionFromPath(path),
    mimeType,
    sizeBytes: new TextEncoder().encode(content).length,
    content,
    createdAt: String(record.created_at || '').trim() || undefined,
    modifiedAt: String(record.modified_at || '').trim() || undefined,
    previewKind,
    previewable: previewKind !== 'unknown',
  }
}

function artifactFromToolEntry(value: ExecutionToolArtifact): ChatArtifact | null {
  const path = String(value.path || value.relativePath || '').trim()
  if (!path) return null
  const content = String(value.content || '')
  const downloadBase64 = String(value.binaryBase64 || '').trim() || undefined
  const mimeType = String(value.mimeType || '').trim() || inferMimeType(path, content)
  const previewKind = normalizePreviewKind(value.previewKind) || inferPreviewKind(path, mimeType, content)
  const sizeBytes = Number.isFinite(Number(value.sizeBytes)) && Number(value.sizeBytes) > 0
    ? Number(value.sizeBytes)
    : downloadBase64
      ? estimateBase64Size(downloadBase64)
      : new TextEncoder().encode(content).length
  return {
    path,
    name: String(value.name || fileNameFromPath(path)).trim() || fileNameFromPath(path),
    extension: extensionFromPath(path),
    mimeType,
    sizeBytes,
    content,
    downloadBase64,
    createdAt: String(value.createdAt || '').trim() || undefined,
    modifiedAt: String(value.modifiedAt || '').trim() || undefined,
    previewKind,
    previewable: previewKind !== 'unknown',
  }
}

export function extractArtifactsFromState(values: Record<string, unknown>): Map<string, ChatArtifact> {
  const files = asRecord(values.files)
  const artifacts = new Map<string, ChatArtifact>()
  Object.entries(files).forEach(([path, value]) => {
    if (!path.startsWith('/')) return
    const artifact = artifactFromStateEntry(path, value)
    if (!artifact) return
    artifacts.set(path, artifact)
  })
  return artifacts
}

export function sortArtifacts(artifacts: Iterable<ChatArtifact>): ChatArtifact[] {
  return Array.from(artifacts).sort((left, right) => {
    const rightTime = Math.max(artifactTimestamp(right.modifiedAt), artifactTimestamp(right.createdAt))
    const leftTime = Math.max(artifactTimestamp(left.modifiedAt), artifactTimestamp(left.createdAt))
    if (rightTime !== leftTime) return rightTime - leftTime
    return left.name.localeCompare(right.name)
  })
}

export function extractArtifactsFromToolCalls(
  toolCallsByMessage: Map<string, ExecutionToolCall[]>,
): Map<string, ChatArtifact> {
  const artifacts = new Map<string, ChatArtifact>()
  toolCallsByMessage.forEach((toolCalls) => {
    toolCalls.forEach((tool) => {
      tool.artifacts.forEach((value) => {
        const artifact = artifactFromToolEntry(value)
        if (!artifact) return
        artifacts.set(artifact.path, artifact)
      })
    })
  })
  return artifacts
}

export function buildMessageArtifactMap(
  toolCallsByMessage: Map<string, ExecutionToolCall[]>,
  artifactsByPath: Map<string, ChatArtifact>,
): Map<string, ChatArtifact[]> {
  const map = new Map<string, ChatArtifact[]>()

  toolCallsByMessage.forEach((toolCalls, messageId) => {
    const seen = new Set<string>()
    const artifacts: ChatArtifact[] = []
    const addArtifact = (artifact: ChatArtifact | null | undefined) => {
      if (!artifact || seen.has(artifact.path)) return
      seen.add(artifact.path)
      artifacts.push(artifact)
    }
    toolCalls.forEach((tool) => {
      const toolName = String(tool.name || '').trim().toLowerCase()
      const filePath = String(tool.filePath || '').trim()
      if (filePath && FILE_OUTPUT_TOOL_NAMES.has(toolName)) {
        addArtifact(artifactsByPath.get(filePath))
      }
      tool.artifacts.forEach((value) => addArtifact(artifactFromToolEntry(value)))
    })
    if (artifacts.length > 0) {
      map.set(messageId, artifacts)
    }
  })

  return map
}
