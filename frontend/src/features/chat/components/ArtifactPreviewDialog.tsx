import { useEffect, useMemo, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Download, ExternalLink, FileText, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { MarkdownMessage } from './MarkdownMessage'
import { cn } from '@/shared/utils/cn'
import { formatBytes } from '../hooks/chatStreamHelpers'
import type { ChatArtifact } from '../artifactUtils'
import {
  canOpenArtifactLocally,
  createArtifactObjectUrl,
  downloadArtifact,
  fetchArtifactTextContent,
  openArtifactLocally,
  revokeArtifactObjectUrl,
} from '../artifactActions'

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

export function ArtifactPreviewDialog({
  artifact,
  open,
  onOpenChange,
}: ArtifactPreviewDialogProps) {
  const [isOpeningLocal, setIsOpeningLocal] = useState(false)
  const [loadedTextContent, setLoadedTextContent] = useState('')
  const [textContentError, setTextContentError] = useState('')
  const blobUrl = useMemo(() => createArtifactObjectUrl(artifact), [artifact])
  const previewTextContent = artifact?.content || loadedTextContent

  useEffect(() => {
    if (!blobUrl) return undefined
    return () => revokeArtifactObjectUrl(blobUrl)
  }, [blobUrl])

  useEffect(() => {
    setLoadedTextContent('')
    setTextContentError('')
    if (
      !artifact
      || artifact.content
      || !canOpenArtifactLocally(artifact)
      || !['markdown', 'json', 'text'].includes(artifact.previewKind)
    ) {
      return undefined
    }

    let cancelled = false
    void fetchArtifactTextContent(artifact)
      .then((content) => {
        if (cancelled) return
        setLoadedTextContent(content)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setTextContentError(String((error as Error)?.message || 'Failed to load preview.'))
      })

    return () => {
      cancelled = true
    }
  }, [artifact])

  const handleOpenLocal = async () => {
    if (!artifact || !canOpenArtifactLocally(artifact) || isOpeningLocal) return
    setIsOpeningLocal(true)
    try {
      await openArtifactLocally(artifact)
    } catch (error: unknown) {
      toast.error(String((error as Error)?.message || 'Failed to open local file.'))
    } finally {
      setIsOpeningLocal(false)
    }
  }

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
                  {artifact.displayPath}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              {artifact && blobUrl && (
                <>
                  <button
                    type="button"
                    onClick={() => downloadArtifact(artifact)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download
                  </button>
                  <button
                    type="button"
                    onClick={() => window.open(blobUrl, '_blank', 'noopener,noreferrer')}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)]"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open
                  </button>
                </>
              )}
              {artifact && canOpenArtifactLocally(artifact) && (
                <button
                  type="button"
                  onClick={() => void handleOpenLocal()}
                  disabled={isOpeningLocal}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-panel-alt)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {isOpeningLocal ? 'Opening…' : 'Open local'}
                </button>
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
                {previewTextContent
                  ? <MarkdownMessage content={previewTextContent} />
                  : (
                      <div className="text-sm text-[var(--color-text-muted)]">
                        {textContentError || 'Loading preview…'}
                      </div>
                    )}
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

            {artifact?.previewKind === 'image-data-url' && blobUrl && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-white p-6">
                <img src={blobUrl} alt={artifact.name} className="mx-auto max-h-[68vh] max-w-full object-contain" />
              </div>
            )}

            {artifact?.previewKind === 'pdf-data-url' && blobUrl && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)]">
                <iframe
                  title={artifact.name}
                  src={blobUrl}
                  className="h-[68vh] w-full"
                />
              </div>
            )}

            {artifact?.previewKind === 'json' && (
              <pre className="overflow-auto rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)] p-5 font-mono text-[12px] leading-6 text-[var(--color-text)]">
                {previewTextContent
                  ? safeJsonPreview(previewTextContent)
                  : (textContentError || 'Loading preview…')}
              </pre>
            )}

            {artifact?.previewKind === 'text' && (
              <div className="overflow-hidden rounded-[24px] border border-[var(--color-border)] bg-[var(--color-panel)]">
                <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
                  <FileText className="h-3.5 w-3.5" />
                  File preview
                </div>
                <pre className="max-h-[68vh] overflow-auto p-5 font-mono text-[12px] leading-6 text-[var(--color-text)]">
                  {previewTextContent || textContentError || 'Loading preview…'}
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
                      {canOpenArtifactLocally(artifact)
                        ? 'Inline preview is not available for this file type. Open the local file or download it to inspect the final deliverable.'
                        : 'Inline preview is not available for this file type. Use Download or Open to inspect it.'}
                    </div>
                  )
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
