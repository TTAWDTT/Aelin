import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/shared/utils/cn'

interface MarkdownMessageProps {
  content: string
  compact?: boolean
}

function normalizeMarkdownContent(content: string): string {
  const raw = String(content || '').replace(/\r\n/g, '\n').trim()
  if (!raw) return ''

  const lines = raw.split('\n')
  const normalized: string[] = []

  for (const line of lines) {
    const current = line.replace(/^(#{1,6})(\S)/, '$1 $2')
    const isBlockStart =
      /^(#{1,6}\s|```|~~~|---\s*$|\*\*\*\s*$|___\s*$)/.test(current.trim())
    const previous = normalized.at(-1) ?? ''
    if (isBlockStart && previous.trim()) {
      normalized.push('')
    }
    normalized.push(current)
  }

  return normalized.join('\n').replace(/\n{3,}/g, '\n\n')
}

export function MarkdownMessage({ content, compact = false }: MarkdownMessageProps) {
  const normalizedContent = normalizeMarkdownContent(content)

  return (
    <div
      className={cn(
        'prose prose-sm max-w-none break-words prose-neutral [overflow-wrap:anywhere]',
        '[&_a]:break-all [&_blockquote]:my-3 [&_blockquote]:rounded-r-2xl [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--color-border-strong)] [&_blockquote]:bg-[var(--color-bg-elevated)] [&_blockquote]:px-3 [&_blockquote]:py-2',
        '[&_code]:break-all [&_li]:my-1 [&_ol]:my-2 [&_p]:my-2 [&_pre]:my-3 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_table]:my-3 [&_table]:max-w-full [&_ul]:my-2',
      )}
      style={{
        fontFamily: 'var(--font-body)',
        lineHeight: compact ? 1.58 : 1.68,
        fontSize: compact ? '0.88rem' : '0.94rem',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="mb-2 mt-3 text-[1.02rem] font-semibold">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-3 text-[0.98rem] font-semibold">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1.5 mt-3 text-[0.94rem] font-semibold">{children}</h3>,
          p: ({ children }) => <p className="leading-7 text-[var(--color-text)]">{children}</p>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-[var(--color-blue)] underline decoration-[color:var(--color-border-strong)] underline-offset-3"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-2xl border border-[var(--color-border)]">
              <table className="min-w-full border-collapse text-left text-[0.85rem]">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-[var(--color-bg-elevated)]">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-[var(--color-border)] px-3 py-2 font-semibold text-[var(--color-text)]">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-[var(--color-border)] px-3 py-2 align-top text-[var(--color-text-muted)]">
              {children}
            </td>
          ),
          code: ({ inline, className, children, ...props }: any) =>
            inline ? (
              <code
                className={cn(
                  'rounded-md border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-1.5 py-0.5 text-[0.84em] text-[var(--color-text)]',
                  className,
                )}
                {...props}
              >
                {children}
              </code>
            ) : (
              <code
                className={cn(
                  'block whitespace-pre-wrap text-[0.84rem] leading-6 text-[var(--color-text)]',
                  className,
                )}
                {...props}
              >
                {children}
              </code>
            ),
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-3">
              {children}
            </pre>
          ),
          hr: () => <hr className="my-3 border-none border-t border-[var(--color-border)]" />,
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  )
}
