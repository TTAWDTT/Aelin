import { fetchJson, fetchText } from '@/shared/api/client'
import type { ChatArtifact } from './artifactUtils'

type ArtifactLocalOpenResponse = {
  path: string
  opened: boolean
  detail: string
}

function decodeBase64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = window.atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
}

function buildArtifactContentUrl(
  artifact: ChatArtifact,
  options: { download?: boolean } = {},
): string {
  if (!canOpenArtifactLocally(artifact)) return ''
  const { download = false } = options
  const params = new URLSearchParams({ path: artifact.localPath })
  if (download) {
    params.set('download', '1')
  }
  return `/api/v1/aelin/artifact/content?${params.toString()}`
}

function isTextPreviewKind(previewKind: string): boolean {
  return previewKind === 'markdown' || previewKind === 'json' || previewKind === 'text'
}

export function createArtifactObjectUrl(artifact: ChatArtifact | null): string {
  if (!artifact) return ''
  if (
    artifact.previewKind === 'image-data-url'
    || artifact.previewKind === 'pdf-data-url'
  ) {
    if (artifact.content) {
      return artifact.content
    }
    return canOpenArtifactLocally(artifact) ? buildArtifactContentUrl(artifact) : ''
  }
  if (artifact.downloadBase64) {
    const blob = new Blob([decodeBase64ToArrayBuffer(artifact.downloadBase64)], {
      type: artifact.mimeType || 'application/octet-stream',
    })
    return URL.createObjectURL(blob)
  }
  if (!artifact.content && canOpenArtifactLocally(artifact)) {
    return buildArtifactContentUrl(artifact)
  }
  return URL.createObjectURL(new Blob([artifact.content], { type: artifact.mimeType || 'text/plain' }))
}

export function revokeArtifactObjectUrl(url: string): void {
  if (!url || url.startsWith('data:') || url.startsWith('/api/')) return
  URL.revokeObjectURL(url)
}

export function downloadArtifact(artifact: ChatArtifact): void {
  const url = canOpenArtifactLocally(artifact)
    ? buildArtifactContentUrl(artifact, { download: true })
    : createArtifactObjectUrl(artifact)
  if (!url) return
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = artifact.name
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  if (!url.startsWith('data:') && !url.startsWith('/api/')) {
    window.setTimeout(() => revokeArtifactObjectUrl(url), 0)
  }
}

export function canOpenArtifactLocally(
  artifact: ChatArtifact | null | undefined,
): artifact is ChatArtifact & { localPath: string } {
  return Boolean(artifact?.localPath)
}

export async function fetchArtifactTextContent(artifact: ChatArtifact): Promise<string> {
  if (artifact.content) return artifact.content
  if (!canOpenArtifactLocally(artifact) || !isTextPreviewKind(artifact.previewKind)) {
    return ''
  }
  const url = buildArtifactContentUrl(artifact)
  if (!url) return ''
  return fetchText(url)
}

export async function openArtifactLocally(
  artifact: ChatArtifact,
): Promise<ArtifactLocalOpenResponse> {
  if (!canOpenArtifactLocally(artifact)) {
    throw new Error('Local open is unavailable for this artifact.')
  }
  return fetchJson<ArtifactLocalOpenResponse>('/api/v1/aelin/device/path/open', {
    method: 'POST',
    body: JSON.stringify({ path: artifact.localPath }),
  })
}
