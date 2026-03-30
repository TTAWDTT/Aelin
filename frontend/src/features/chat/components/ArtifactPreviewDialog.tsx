import { useEffect, useMemo } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Download, ExternalLink, FileText, X } from 'lucide-react'
import { MarkdownMessage } from './MarkdownMessage'
import { cn } from '@/shared/utils/cn'
import { formatBytes } from '../hooks/chatStreamHelpers'
import type { ChatArtifact } from '../artifactUtils'

interface ArtifactPreviewDialogProps {
  artifact: ChatArtifact | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function safeJsonPreview(content: string): string {
  try {
    return JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    return content
  }
}

function decodeBase64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = window.atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
}

function createBlobUrl(artifact: ChatArtifact | null): string {
  if (!artifact) return ''
  if (
    artifact.previewKind === 'image-data-url'
    || artifact.previewKind === 'pdf-data-url'
  ) {
    return artifact.content
  }
  if (artifact.downloadBase64) {
    const blob = new Blob([decodeBase64ToArrayBuffer(artifact.downloadBase64)], {
      type: artifact.mimeType || 'application/octet-stream',
    })
    return URL.createObjectURL(blob)
  }
  const blob = new Blob([artifact.content], { type: artifact.mimeType || 'text/plain' })
  return URL.createObjectURL(blob)
}

export function ArtifactPreviewDialog({
  artifact,
  open,
  onOpenChange,
}: ArtifactPreviewDialogProps) {
  const blobUrl = useMemo(() => createBlobUrl(artifact), [artifact])

  useEffect(() => {
    if (!blobUrl || blobUrl.startsWith('data:')) return undefined
    return () => URL.revokeObjectURL(blobUrl)
  }, [blobUrl])

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px]" />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 flex w-[min(96vw,1080px)] max-w-[1080px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[28px] border border-[var(--color-border)] bg-[var(--color-panel)] shadow-[0_28px_120px_-36px_rgba(0,0,0,0.45)]',
            'max-h-[92vh]',
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="truncate text-base font-semibold text-[var(--color-text)]">
                {artifact?.name || 'Artifact preview'}
              </Dialog.Title>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
                <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-0.5">
                  {artifact?.mimeType || 'unknown'}
                </span>
                {artifact && (
                  <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-2 py-0.5">
                    {formatBytes(artifact.sizeBytes)}
                  </span>
                )}
                {artifact?.modifiedAt && (
                  <span className="truncate">{artifact.modifiedAt}</span>
                )}
              </div>
              {artifact?.path && (
                <div className="mt-2 truncate font-mono text-[11px] text-[var(--color-text-muted)]">
                  {artifact.path}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              {artifact && blobUrl && (
                <>
                  <a
                    href={blobUrl}
                    download={artifact.name}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download
                  </a>
                  <a
                    href={blobUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open
                  </a>
                </>
              )}
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-panel-alt)] hover:text-[var(--color-text)]"
                  aria-label="Close preview"
                >
                  <X className="h-4 w-4" />
                </button>
              </Dialog.Close>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto bg-[var(--color-bg)] p-4">
            {!artifact && (
              <div className="rounded-[24px] border border-dashed border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-10 text-center text-sm text-[var(--color-text-muted)]">
                No artifact selected.
              </div>
            )}

            {artifact?.previewKind === 'markdown' && (
              <div className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
                <MarkdownMessage content={artifact.content} />
              </div>
            )}

            {artifact?.previewKind === 'html' && blobUrl && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-white">
                <iframe
                  title={artifact.name}
                  src={blobUrl}
                  sandbox="allow-same-origin"
                  className="h-[68vh] w-full bg-white"
                />
              </div>
            )}

            {artifact?.previewKind === 'svg' && blobUrl && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-white p-6">
                <img src={blobUrl} alt={artifact.name} className="mx-auto max-h-[68vh] max-w-full object-contain" />
              </div>
            )}

            {artifact?.previewKind === 'image-data-url' && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-white p-6">
                <img src={artifact.content} alt={artifact.name} className="mx-auto max-h-[68vh] max-w-full object-contain" />
              </div>
            )}

            {artifact?.previewKind === 'pdf-data-url' && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)]">
                <iframe
                  title={artifact.name}
                  src={artifact.content}
                  className="h-[68vh] w-full"
                />
              </div>
            )}

            {artifact?.previewKind === 'json' && (
              <pre className="overflow-auto rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)] p-5 font-mono text-[12px] leading-6 text-[var(--color-text)]">
                {safeJsonPreview(artifact.content)}
              </pre>
            )}

            {artifact?.previewKind === 'text' && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)]">
                <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
                  <FileText className="h-3.5 w-3.5" />
                  File preview
                </div>
                <pre className="max-h-[68vh] overflow-auto p-5 font-mono text-[12px] leading-6 text-[var(--color-text)]">
                  {artifact.content}
                </pre>
              </div>
            )}

            {artifact?.previewKind === 'unknown' && (
              artifact.content
                ? (
                    <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)]">
                      <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
                        <FileText className="h-3.5 w-3.5" />
                        File preview
                      </div>
                      <pre className="max-h-[68vh] overflow-auto p-5 font-mono text-[12px] leading-6 text-[var(--color-text)]">
                        {artifact.content}
                      </pre>
                    </div>
                  )
                : (
                    <div className="rounded-[24px] border border-dashed border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-10 text-center text-sm text-[var(--color-text-muted)]">
                      Preview is not available for this file type. Use Download or Open to inspect it.
                    </div>
                  )
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
