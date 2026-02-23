import { cn } from '@/shared/utils/cn'
import { relativeTime } from '@/shared/utils/format'
import type { ChangePreviewRow } from '../types'

type Props = {
  contextTargetId: number
  changeStreamLoading: boolean
  changePreviewRows: ChangePreviewRow[]
  onOpenExternal: (url: string | null | undefined) => void
  onLinkTarget: (targetId: number) => void
}

export function ChangeStreamSection({
  contextTargetId,
  changeStreamLoading,
  changePreviewRows,
  onOpenExternal,
  onLinkTarget,
}: Props) {
  return (
    <section className="mb-3 rounded-[12px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] p-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[12px] font-semibold text-[var(--color-text)]">
            {contextTargetId > 0 ? '追踪变更流 (当前联动)' : '追踪变更流 (全部)'}
          </p>
          <p className="text-[11px] text-[var(--color-text-muted)]">
            {contextTargetId > 0 ? '只显示当前目标变更' : '聚合所有追踪目标的最新变更'}
          </p>
        </div>
      </div>

      <div className="max-h-[250px] space-y-2 overflow-y-auto pr-1">
        {changePreviewRows.map(({ row: change, preview }) => (
          <article
            key={`tracking-change-${change.id}`}
            className={cn(
              'aelin-card p-2',
              preview.url ? 'cursor-pointer hover:border-[var(--color-border-strong)]' : ''
            )}
            onClick={() => {
              if (preview.url) onOpenExternal(preview.url)
            }}
            onKeyDown={(event) => {
              if (!preview.url) return
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onOpenExternal(preview.url)
              }
            }}
            role={preview.url ? 'button' : undefined}
            tabIndex={preview.url ? 0 : -1}
          >
            <div className="mb-1 flex items-start justify-between gap-2">
              <p className="line-clamp-1 text-[12px] font-medium">{change.title || '变更'}</p>
              <span className="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                {change.severity || 'info'}
              </span>
            </div>

            {preview.imageUrl ? (
              <div className="mb-1.5 flex gap-2">
                <div className="h-16 w-24 shrink-0 overflow-hidden rounded-[8px] border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
                  <img src={preview.imageUrl} alt={preview.title} className="h-full w-full object-cover" loading="lazy" />
                </div>
                <div className="min-w-0">
                  <p className="line-clamp-2 text-[11px] font-medium text-[var(--color-text)]">
                    {preview.title}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-[11px] text-[var(--color-text-muted)]">
                    {change.summary || '本次变更暂无摘要。'}
                  </p>
                </div>
              </div>
            ) : (
              <div className="mb-1.5">
                <p className="line-clamp-2 text-[11px] font-medium text-[var(--color-text)]">
                  {preview.title}
                </p>
                <p className="mt-0.5 line-clamp-2 text-[11px] text-[var(--color-text-muted)]">
                  {change.summary || '本次变更暂无摘要。'}
                </p>
              </div>
            )}

            <p className="line-clamp-1 text-[11px] text-[var(--color-text-muted)]">
              {change.target_name}
              {change.target_source ? ` · ${change.target_source}` : ''}
              {change.created_at ? ` · ${relativeTime(change.created_at) || change.created_at}` : ''}
            </p>

            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {preview.url ? (
                <button
                  onClick={(event) => {
                    event.stopPropagation()
                    onOpenExternal(preview.url)
                  }}
                  className="aelin-btn h-7 px-2 text-[11px]"
                >
                  {'查看来源'}
                </button>
              ) : null}
              {contextTargetId <= 0 && change.target_id ? (
                <button
                  onClick={(event) => {
                    event.stopPropagation()
                    onLinkTarget(change.target_id)
                  }}
                  className="aelin-btn h-7 px-2 text-[11px]"
                >
                  {'联动到该目标'}
                </button>
              ) : null}
            </div>
          </article>
        ))}

        {changePreviewRows.length === 0 ? (
          <p className="py-4 text-center text-[11px] text-[var(--color-text-muted)]">
            {changeStreamLoading ? '变更加载中…' : '暂无变更'}
          </p>
        ) : null}
      </div>
    </section>
  )
}
