import { ExternalLink } from 'lucide-react'
import type { DeskFeedItem } from '@/shared/api/types'
import { relativeTime } from '@/shared/utils/format'

type Props = {
  items: DeskFeedItem[]
  emptyHint: string
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => Promise<void> | void
}

export function FeedItemsSection({ items, emptyHint, hasMore, loadingMore, onLoadMore }: Props) {
  return (
    <>
      <div className="space-y-2.5">
        {items.map((item) => (
          <article key={item.message_id} className="aelin-card p-2.5">
            <div className="mb-1 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-[12px] font-semibold">{item.sender || item.source_label}</p>
                <p className="truncate text-[11px] text-[var(--color-text-muted)]">
                  {item.source_label} · {relativeTime(item.received_at) || item.received_at}
                </p>
              </div>
              {item.external_url ? (
                <a
                  href={item.external_url}
                  target="_blank"
                  rel="noreferrer"
                  className="aelin-btn h-7 px-2 text-[11px]"
                  title="查看原文"
                >
                  <ExternalLink size={12} />
                </a>
              ) : null}
            </div>

            <h3 className="mb-1.5 line-clamp-2 text-[13px] font-semibold">{item.title}</h3>
            {item.image_url ? (
              <img
                src={item.image_url}
                alt={item.title}
                className="mb-2 max-h-[220px] w-full rounded-[10px] border border-[var(--color-border)] object-cover"
                loading="lazy"
              />
            ) : null}
            {!!item.preview && (
              <p className="line-clamp-3 text-[12px] text-[var(--color-text-muted)]">{item.preview}</p>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(item.tags || []).slice(0, 5).map((tag) => (
                <span
                  key={`${item.message_id}-${tag}`}
                  className={`rounded-full border px-2 py-0.5 text-[10px] ${
                    tag === item.primary_tag
                      ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-[var(--color-bg)]'
                      : 'border-[var(--color-border)] text-[var(--color-text-muted)]'
                  }`}
                >
                  {tag}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>

      {items.length === 0 && (
        <div className="py-12 text-center text-[12px] text-[var(--color-text-muted)]">{emptyHint}</div>
      )}

      {hasMore && items.length > 0 && (
        <div className="mt-3 flex justify-center">
          <button onClick={() => void onLoadMore()} disabled={loadingMore} className="aelin-btn h-8 px-3 text-[11px]">
            {loadingMore ? '加载中…' : '加载更多'}
          </button>
        </div>
      )}
    </>
  )
}
