import type { ReactNode } from 'react'
import { cn } from '@/shared/utils/cn'

interface PageScaffoldProps {
  title: string
  subtitle?: string
  headerActions?: ReactNode
  headerActionsFullWidth?: boolean
  children: ReactNode
  className?: string
  contentClassName?: string
}

export function PageScaffold({
  title,
  subtitle,
  headerActions,
  headerActionsFullWidth = false,
  children,
  className,
  contentClassName,
}: PageScaffoldProps) {
  return (
    <section className={cn('aelin-page', className)}>
      <header className={cn('aelin-page-header min-w-0', headerActionsFullWidth && 'flex-wrap items-start')}>
        <div className="min-w-0">
          <h1 className="aelin-page-title truncate">{title}</h1>
          {subtitle && <p className="aelin-page-subtitle truncate">{subtitle}</p>}
        </div>
        {headerActions && (
          <div
            className={cn(
              headerActionsFullWidth
                ? 'min-w-0 w-full overflow-visible'
                : 'min-w-0 w-full sm:w-auto sm:max-w-full sm:shrink-0'
            )}
          >
            {headerActions}
          </div>
        )}
      </header>
      <div className={cn('aelin-page-content', contentClassName)}>{children}</div>
    </section>
  )
}

