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
  displayPath: string
  name: string
  extension: string
  mimeType: string
  sizeBytes: number
  content: string
  downloadBase64?: string
  relativePath?: string
  localPath?: string
  createdAt?: string
  modifiedAt?: string
  previewKind: ArtifactPreviewKind
  previewable: boolean
}

type RuntimeCapabilityPaths = {
  workspaceLocalPath?: string
  outputsLocalPath?: string
}

const REFERENCED_ARTIFACT_PATH_PATTERN = /((?:\/(?:outputs|workspace)\/[^\s`"'<>]+)|(?:[a-z]:[\\/][^\s`"'<>]+))/gi

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

const INTERNAL_ARTIFACT_PREFIXES = [
  '/attachments/',
  '/memory/',
  '/runtime/',
  '/skills/',
] as const

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
  const segments = normalized.split(/[\\/]/).filter(Boolean)
  return segments.at(-1) || normalized
}

function extensionFromPath(path: string): string {
  const name = fileNameFromPath(path)
  const match = /\.([a-z0-9_-]+)$/i.exec(name)
  return match ? match[1].toLowerCase() : ''
}

function normalizeLocalFsPath(path: string): string {
  return String(path || '').trim().replace(/\\/g, '/')
}

function joinLocalFsPath(root: string, suffix: string): string {
  const normalizedRoot = normalizeLocalFsPath(root).replace(/\/+$/, '')
  const normalizedSuffix = String(suffix || '').trim().replace(/\\/g, '/').replace(/^\/+/, '')
  if (!normalizedRoot) return normalizedSuffix
  if (!normalizedSuffix) return normalizedRoot
  return `${normalizedRoot}/${normalizedSuffix}`
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
    case 'doc':
      return 'application/msword'
    case 'docx':
      return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    case 'ppt':
      return 'application/vnd.ms-powerpoint'
    case 'pptx':
      return 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    case 'xls':
      return 'application/vnd.ms-excel'
    case 'xlsx':
      return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
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

function isAbsoluteArtifactPath(path: string): boolean {
  const text = String(path || '').trim()
  if (!text) return false
  if (/^\/(?:outputs|workspace)(?:\/|$)/i.test(text)) return false
  return /^[a-z]:[\\/]/i.test(text) || /^\\\\[^\\]/.test(text) || /^\/(?!\/)/.test(text)
}

function shouldIgnoreStateArtifactPath(path: string): boolean {
  const normalized = String(path || '').trim()
  if (!normalized.startsWith('/')) return true
  return INTERNAL_ARTIFACT_PREFIXES.some((prefix) => normalized.startsWith(prefix))
}

function parseRuntimeCapabilityPaths(values: Record<string, unknown>): RuntimeCapabilityPaths {
  const files = asRecord(values.files)
  const rawCapabilities = asRecord(files['/runtime/capabilities.json'])
  const capabilitiesText = contentToString(rawCapabilities.content)
  if (!capabilitiesText.trim()) return {}

  try {
    const parsed = JSON.parse(capabilitiesText)
    const record = asRecord(parsed)
    const workspaceLocalPath = normalizeLocalFsPath(String(record.workspace_local_path || ''))
    const outputsLocalPath = normalizeLocalFsPath(String(record.outputs_local_path || ''))
    return {
      workspaceLocalPath: workspaceLocalPath || undefined,
      outputsLocalPath: outputsLocalPath || undefined,
    }
  } catch {
    return {}
  }
}

function resolveStateArtifactLocalPath(
  path: string,
  runtimePaths: RuntimeCapabilityPaths,
): string | undefined {
  const normalized = String(path || '').trim()
  if (!normalized.startsWith('/')) return undefined
  if (isAbsoluteArtifactPath(normalized)) return normalizeLocalFsPath(normalized)

  if (normalized === '/workspace' || normalized.startsWith('/workspace/')) {
    const root = runtimePaths.workspaceLocalPath
    if (!root) return undefined
    return joinLocalFsPath(root, normalized.slice('/workspace/'.length))
  }

  if (normalized === '/outputs' || normalized.startsWith('/outputs/')) {
    const root = runtimePaths.outputsLocalPath
    if (!root) return undefined
    return joinLocalFsPath(root, normalized.slice('/outputs/'.length))
  }

  return undefined
}

function artifactFromStateEntry(
  path: string,
  value: unknown,
  runtimePaths: RuntimeCapabilityPaths,
): ChatArtifact | null {
  const record = asRecord(value)
  const content = contentToString(record.content)
  if (!content && !record.created_at && !record.modified_at) return null
  const mimeType = inferMimeType(path, content)
  const previewKind = inferPreviewKind(path, mimeType, content)
  const localPath = resolveStateArtifactLocalPath(path, runtimePaths)
  return {
    path,
    displayPath: path,
    name: fileNameFromPath(path),
    extension: extensionFromPath(path),
    mimeType,
    sizeBytes: new TextEncoder().encode(content).length,
    content,
    localPath,
    createdAt: String(record.created_at || '').trim() || undefined,
    modifiedAt: String(record.modified_at || '').trim() || undefined,
    previewKind,
    previewable: previewKind !== 'unknown' || Boolean(localPath),
  }
}

function artifactFromToolEntry(value: ExecutionToolArtifact): ChatArtifact | null {
  const path = String(value.path || value.relativePath || '').trim()
  if (!path) return null
  const content = String(value.content || '')
  const relativePath = String(value.relativePath || '').trim() || undefined
  const localPath = relativePath && isAbsoluteArtifactPath(path) ? path : undefined
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
    displayPath: relativePath || path,
    name: String(value.name || fileNameFromPath(path)).trim() || fileNameFromPath(path),
    extension: extensionFromPath(path),
    mimeType,
    sizeBytes,
    content,
    downloadBase64,
    relativePath,
    localPath,
    createdAt: String(value.createdAt || '').trim() || undefined,
    modifiedAt: String(value.modifiedAt || '').trim() || undefined,
    previewKind,
    previewable: previewKind !== 'unknown' || Boolean(localPath),
  }
}

export function extractArtifactsFromState(values: Record<string, unknown>): Map<string, ChatArtifact> {
  const files = asRecord(values.files)
  const runtimePaths = parseRuntimeCapabilityPaths(values)
  const artifacts = new Map<string, ChatArtifact>()
  Object.entries(files).forEach(([path, value]) => {
    if (shouldIgnoreStateArtifactPath(path)) return
    const artifact = artifactFromStateEntry(path, value, runtimePaths)
    if (!artifact) return
    artifacts.set(path, artifact)
  })
  return artifacts
}

export function artifactFromServerPayload(value: unknown): ChatArtifact | null {
  const record = asRecord(value)
  const path = String(
    record.path
    || record.abs_path
    || record.file_path
    || record.relative_path
    || '',
  ).trim()
  if (!path) return null

  const content = contentToString(record.content)
  const relativePath = String(record.relative_path || record.relativePath || '').trim() || undefined
  const localPath = isAbsoluteArtifactPath(path) ? normalizeLocalFsPath(path) : undefined
  const downloadBase64 = String(record.binary_base64 || record.binaryBase64 || '').trim() || undefined
  const mimeType = String(record.mime_type || record.mimeType || '').trim() || inferMimeType(path, content)
  const previewKind = normalizePreviewKind(record.preview_kind || record.previewKind) || inferPreviewKind(path, mimeType, content)
  const sizeBytes = Number.isFinite(Number(record.size_bytes || record.sizeBytes)) && Number(record.size_bytes || record.sizeBytes) > 0
    ? Number(record.size_bytes || record.sizeBytes)
    : downloadBase64
      ? estimateBase64Size(downloadBase64)
      : new TextEncoder().encode(content).length

  return {
    path,
    displayPath: relativePath || path,
    name: String(record.name || fileNameFromPath(path)).trim() || fileNameFromPath(path),
    extension: extensionFromPath(path),
    mimeType,
    sizeBytes,
    content,
    downloadBase64,
    relativePath,
    localPath,
    createdAt: String(record.created_at || record.createdAt || '').trim() || undefined,
    modifiedAt: String(record.modified_at || record.modifiedAt || '').trim() || undefined,
    previewKind,
    previewable: previewKind !== 'unknown' || Boolean(localPath),
  }
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

export function normalizeReferencedArtifactPath(value: string): string {
  return String(value || '')
    .trim()
    .replace(/[)\]}>,;:!?]+$/g, '')
    .replace(/[。；，、]+$/g, '')
    .replace(/\\/g, '/')
}

export function artifactMatchesReferencePath(
  artifact: ChatArtifact | null | undefined,
  path: string,
): boolean {
  if (!artifact) return false
  const normalized = normalizeReferencedArtifactPath(path)
  if (!normalized) return false
  return (
    normalizeReferencedArtifactPath(artifact.path) === normalized
    || normalizeReferencedArtifactPath(artifact.displayPath) === normalized
    || normalizeReferencedArtifactPath(artifact.relativePath || '') === normalized
    || normalizeReferencedArtifactPath(artifact.localPath || '') === normalized
  )
}

function resolveReferencedArtifact(
  path: string,
  artifactsByPath: Map<string, ChatArtifact>,
): ChatArtifact | undefined {
  const normalized = normalizeReferencedArtifactPath(path)
  if (!normalized) return undefined

  const direct = artifactsByPath.get(normalized)
  if (direct) return direct

  return Array.from(artifactsByPath.values()).find((artifact) => artifactMatchesReferencePath(artifact, normalized))
}

export function extractReferencedArtifactPaths(content: string): string[] {
  const text = String(content || '')
  if (!text.trim()) return []

  const matches = text.match(REFERENCED_ARTIFACT_PATH_PATTERN) || []
  const seen = new Set<string>()
  const paths: string[] = []
  matches.forEach((match) => {
    const normalized = normalizeReferencedArtifactPath(match)
    if (!normalized || seen.has(normalized)) return
    seen.add(normalized)
    paths.push(normalized)
  })
  return paths
}

export function findArtifactsReferencedInText(
  content: string,
  artifactsByPath: Map<string, ChatArtifact>,
): ChatArtifact[] {
  if (artifactsByPath.size === 0) return []
  const matches = extractReferencedArtifactPaths(content)
  const seen = new Set<string>()
  const artifacts: ChatArtifact[] = []

  matches.forEach((match) => {
    const artifact = resolveReferencedArtifact(match, artifactsByPath)
    if (!artifact || seen.has(artifact.path)) return
    seen.add(artifact.path)
    artifacts.push(artifact)
  })

  return sortArtifacts(artifacts)
}

export function artifactHasInlinePreview(
  artifact: ChatArtifact | null | undefined,
): boolean {
  if (!artifact) return false
  if (artifact.previewKind === 'unknown') return false
  return Boolean(artifact.content || artifact.localPath || artifact.downloadBase64)
}
