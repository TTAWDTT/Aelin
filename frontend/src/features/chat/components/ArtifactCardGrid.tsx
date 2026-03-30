import { Download, Eye, FileCode2, FileJson2, FileText, Globe, Image as ImageIcon } from 'lucide-react'
import { formatBytes } from '../hooks/chatStreamHelpers'
import type { ChatArtifact } from '../artifactUtils'

interface ArtifactCardGridProps {
  artifacts: ChatArtifact[]
  onOpenArtifact: (artifact: ChatArtifact) => void
}

function iconForArtifact(artifact: ChatArtifact) {
  switch (artifact.previewKind) {
    case 'html':
      return Globe
    case 'svg':
    case 'image-data-url':
      return ImageIcon
    case 'json':
      return FileJson2
    case 'markdown':
      return FileText
    default:
      return FileCode2
  }
}

function createDownloadUrl(artifact: ChatArtifact): string {
  if (
    artifact.previewKind === 'image-data-url'
    || artifact.previewKind === 'pdf-data-url'
  ) {
    return artifact.content
  }
  if (artifact.downloadBase64) {
    const binary = window.atob(artifact.downloadBase64)
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index)
    }
    const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
    return URL.createObjectURL(new Blob([buffer], { type: artifact.mimeType || 'application/octet-stream' }))
  }
  return URL.createObjectURL(new Blob([artifact.content], { type: artifact.mimeType || 'text/plain' }))
}

function downloadArtifact(artifact: ChatArtifact) {
  const url = createDownloadUrl(artifact)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = artifact.name
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  if (!url.startsWith('data:')) {
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

export function ArtifactCardGrid({
  artifacts,
  onOpenArtifact,
}: ArtifactCardGridProps) {
  if (artifacts.length === 0) return null

  return (
    <div className="grid gap-2">
      {artifacts.map((artifact) => {
        const Icon = iconForArtifact(artifact)
        return (
          <div
            key={artifact.path}
            className="rounded-[18px] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-3"
          >
            <div className="flex items-start gap-3">
              <button
                type="button"
                onClick={() => onOpenArtifact(artifact)}
                className="flex min-w-0 flex-1 items-start gap-3 text-left"
              >
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] border border-[var(--color-border)] bg-[var(--color-panel)] text-[var(--color-text-muted)]">
                  <Icon className="h-4.5 w-4.5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-medium text-[var(--color-text)]">
                    {artifact.name}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                    <span>{artifact.mimeType}</span>
                    <span>{formatBytes(artifact.sizeBytes)}</span>
                  </span>
                  <span className="mt-1 block truncate font-mono text-[10px] text-[var(--color-text-muted)]">
                    {artifact.path}
                  </span>
                </span>
              </button>
              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => onOpenArtifact(artifact)}
                  className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                >
                  <Eye className="h-3.5 w-3.5" />
                  Preview
                </button>
                <button
                  type="button"
                  onClick={() => downloadArtifact(artifact)}
                  className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download
                </button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
