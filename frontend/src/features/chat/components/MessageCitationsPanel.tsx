import type { AelinCitation } from '@/shared/api/types'
import { relativeTime, sourceIcon } from '@/shared/utils/format'

interface MessageCitationsPanelProps {
  citations: AelinCitation[]
}

export function MessageCitationsPanel({ citations }: MessageCitationsPanelProps) {
  if (citations.length === 0) return null

  return (
    <details className="group mt-3.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2.5 py-2">
      <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        引用来源 ({citations.length})
      </summary>
      <div className="grid grid-rows-[0fr] transition-[grid-template-rows] duration-300 ease-out group-open:grid-rows-[1fr]">
        <div className="overflow-hidden">
          <div className="mt-2 space-y-1.5 opacity-0 translate-y-1 transition-all duration-300 ease-out group-open:translate-y-0 group-open:opacity-100">
            {citations.map((citation, index) => (
              <div
                key={`${citation.message_id}-${index}`}
                className="flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1.5 text-[11px] sm:flex-nowrap sm:gap-2 sm:px-2.5 sm:text-xs"
              >
                <span>{sourceIcon(citation.source)}</span>
                <span className="min-w-0 flex-1 break-all font-medium sm:truncate">
                  [{index + 1}] {citation.title}
                </span>
                <span className="text-[var(--color-text-muted)]">{citation.source_label}</span>
                <span className="text-[var(--color-text-muted)] sm:inline">{relativeTime(citation.received_at)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </details>
  )
}
