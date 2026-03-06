import type { AelinAction } from '@/shared/api/types'
import { isBrowserConfirmAction, isTrackAction, resolveActionHref } from './messageBubbleUtils'

interface MessageActionsPanelProps {
  actions: AelinAction[]
  isTrackPending: boolean
  isBrowserPending: boolean
  onTrackConfirm: (action: AelinAction) => void
  onBrowserConfirm: (action: AelinAction) => void
}

function ActionCard({
  title,
  detail,
  children,
}: {
  title: string
  detail?: string
  children?: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-2">
      <div className="text-[11px] font-medium text-[var(--color-text)]">{title}</div>
      {detail ? <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">{detail}</div> : null}
      {children}
    </div>
  )
}

export function MessageActionsPanel({
  actions,
  isTrackPending,
  isBrowserPending,
  onTrackConfirm,
  onBrowserConfirm,
}: MessageActionsPanelProps) {
  if (actions.length === 0) return null

  return (
    <details className="group mt-3.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2.5 py-2">
      <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        建议动作 ({actions.length})
      </summary>
      <div className="grid grid-rows-[0fr] transition-[grid-template-rows] duration-300 ease-out group-open:grid-rows-[1fr]">
        <div className="overflow-hidden">
          <div className="mt-2 space-y-1.5 opacity-0 translate-y-1 transition-all duration-300 ease-out group-open:translate-y-0 group-open:opacity-100">
            {actions.map((action, index) => {
              const detail = String(action.detail || '').trim()
              const key = `${String(action.kind || 'action')}-${index}`

              if (isTrackAction(action)) {
                return (
                  <ActionCard key={key} title={action.title} detail={detail}>
                    <button
                      className="aelin-btn mt-2 h-7 px-2 text-[11px]"
                      onClick={() => onTrackConfirm(action)}
                      disabled={isTrackPending}
                    >
                      {isTrackPending ? '处理中…' : '执行'}
                    </button>
                  </ActionCard>
                )
              }

              if (isBrowserConfirmAction(action)) {
                return (
                  <ActionCard key={key} title={action.title} detail={detail}>
                    <button
                      className="aelin-btn mt-2 h-7 px-2 text-[11px]"
                      onClick={() => onBrowserConfirm(action)}
                      disabled={isBrowserPending}
                    >
                      {isBrowserPending ? '处理中…' : '确认并继续'}
                    </button>
                  </ActionCard>
                )
              }

              const href = resolveActionHref(action)
              return (
                <ActionCard key={key} title={action.title} detail={detail}>
                  {href ? (
                    <a className="aelin-btn mt-2 inline-flex h-7 items-center px-2 text-[11px]" href={href}>
                      打开
                    </a>
                  ) : null}
                </ActionCard>
              )
            })}
          </div>
        </div>
      </div>
    </details>
  )
}
