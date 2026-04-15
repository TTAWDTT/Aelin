import toast from 'react-hot-toast'
import { Download, ExternalLink, Eye, FileCode2, FileJson2, FileText, Globe, Image as ImageIcon } from 'lucide-react'
import { formatBytes } from '../hooks/chatStreamHelpers'
import type { ChatArtifact } from '../artifactUtils'
import { canOpenArtifactLocally, downloadArtifact, openArtifactLocally } from '../artifactActions'

interface ArtifactCardGridProps {
  artifacts: ChatArtifact[]
  onOpenArtifact: (artifact: ChatArtifact) => void
  constrained?: boolean
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

export function ArtifactCardGrid({
  artifacts,
  onOpenArtifact,
  constrained = false,
}: ArtifactCardGridProps) {
  if (artifacts.length === 0) return null

  return (
    <div className={constrained ? 'grid min-w-0 max-w-full gap-2' : 'grid w-full min-w-0 max-w-full gap-2'}>
      {artifacts.map((artifact) => {
        const Icon = iconForArtifact(artifact)
        return (
          <div
            key={artifact.path}
            className={
              constrained
                ? 'min-w-0 max-w-full overflow-hidden rounded-[18px] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-3'
                : 'w-full min-w-0 max-w-full overflow-hidden rounded-[18px] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-3'
            }
          >
            <div className={
              constrained
                ? 'flex min-w-0 max-w-full flex-col gap-3'
                : 'flex min-w-0 max-w-full flex-col gap-3 xl:flex-row xl:items-start xl:justify-between'
            }>
              <button
                type="button"
                onClick={() => onOpenArtifact(artifact)}
                className={constrained ? 'flex min-w-0 flex-1 items-start gap-3 text-left' : 'flex min-w-0 w-full flex-1 items-start gap-3 text-left'}
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
                    {artifact.displayPath}
                  </span>
                </span>
              </button>
              <div className={
                constrained
                  ? 'flex min-w-0 max-w-full flex-wrap items-center gap-1.5'
                  : 'flex w-full min-w-0 flex-wrap items-center gap-1.5 xl:w-auto xl:shrink-0 xl:justify-end'
              }>
                <button
                  type="button"
                  onClick={() => onOpenArtifact(artifact)}
                  className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                >
                  <Eye className="h-3.5 w-3.5" />
                  Preview
                </button>
                {canOpenArtifactLocally(artifact) && (
                  <button
                    type="button"
                    onClick={() => {
                      void openArtifactLocally(artifact).catch((error: unknown) => {
                        toast.error(String((error as Error)?.message || 'Failed to open local file.'))
                      })
                    }}
                    className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open file
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => downloadArtifact(artifact)}
                  className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
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
