import type { ReactNode } from 'react'
import { cn } from '@/shared/utils/cn'

interface PageScaffoldProps {
  title: string
  subtitle?: string
  headerActions?: ReactNode
  children: ReactNode
  className?: string
  contentClassName?: string
}

export function PageScaffold({
  title,
  subtitle,
  headerActions,
  children,
  className,
  contentClassName,
}: PageScaffoldProps) {
  return (
    <section className={cn('aelin-page', className)}>
      <header className="aelin-page-header">
        <div className="min-w-0">
          <h1 className="aelin-page-title truncate">{title}</h1>
          {subtitle && <p className="aelin-page-subtitle truncate">{subtitle}</p>}
        </div>
        {headerActions && <div className="min-w-0 w-full sm:w-auto sm:shrink-0">{headerActions}</div>}
      </header>
      <div className={cn('aelin-page-content', contentClassName)}>{children}</div>
    </section>
  )
}
