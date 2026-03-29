import type { ExecutionToolCall } from './executionStreamUtils'

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
  createdAt?: string
  modifiedAt?: string
  previewKind: ArtifactPreviewKind
  previewable: boolean
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

export function buildMessageArtifactMap(
  toolCallsByMessage: Map<string, ExecutionToolCall[]>,
  artifactsByPath: Map<string, ChatArtifact>,
): Map<string, ChatArtifact[]> {
  const map = new Map<string, ChatArtifact[]>()

  toolCallsByMessage.forEach((toolCalls, messageId) => {
    const seen = new Set<string>()
    const artifacts: ChatArtifact[] = []
    toolCalls.forEach((tool) => {
      const toolName = String(tool.name || '').trim().toLowerCase()
      const filePath = String(tool.filePath || '').trim()
      if (!filePath || !FILE_OUTPUT_TOOL_NAMES.has(toolName)) return
      const artifact = artifactsByPath.get(filePath)
      if (!artifact || seen.has(artifact.path)) return
      seen.add(artifact.path)
      artifacts.push(artifact)
    })
    if (artifacts.length > 0) {
      map.set(messageId, artifacts)
    }
  })

  return map
}
