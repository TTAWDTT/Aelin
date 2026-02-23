import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BookOpenText, Search } from 'lucide-react'
import { aelinApi } from '@/shared/api/aelin'
import { relativeTime } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { PageScaffold } from '@/shared/components/PageScaffold'

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'web', label: 'Web' },
  { value: 'rss', label: 'RSS' },
  { value: 'x', label: 'X' },
]

export function DiaryView() {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [selectedPath, setSelectedPath] = useState<string>('')

  const { data, isLoading } = useQuery({
    queryKey: ['diary-files', query, source],
    queryFn: () =>
      aelinApi.fileMemorySearch({
        workspace: 'default',
        query,
        source,
        limit: '80',
      }),
  })

  const items = data?.items ?? []

  const { data: fileContent, isLoading: contentLoading } = useQuery({
    queryKey: ['diary-file-content', selectedPath],
    queryFn: () =>
      aelinApi.fileMemoryContent({
        workspace: 'default',
        path: selectedPath,
      }),
    enabled: Boolean(selectedPath),
  })

  useEffect(() => {
    if (!items.length) {
      setSelectedPath('')
      return
    }
    if (!selectedPath || !items.some((item) => item.path === selectedPath)) {
      setSelectedPath(items[0].path)
    }
  }, [items, selectedPath])

  const selectedItem = useMemo(
    () => items.find((item) => item.path === selectedPath) ?? null,
    [items, selectedPath],
  )

  return (
    <PageScaffold title="Aelinの日记" subtitle="OpenViking 记忆文件流">
      <div className="flex h-full min-h-0 flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              className="aelin-input pl-8"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索日记关键词"
            />
          </div>
          <select className="aelin-select w-full sm:w-[116px]" value={source} onChange={(event) => setSource(event.target.value)}>
            {SOURCE_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="aelin-card min-h-0 overflow-y-auto">
            <div className="aelin-list-divider">
              {items.map((item) => (
                <button
                  key={item.path}
                  onClick={() => setSelectedPath(item.path)}
                  className={cn(
                    'w-full px-3 py-2.5 text-left transition-colors hover:bg-[var(--color-accent-soft)]',
                    selectedPath === item.path && 'bg-[var(--color-accent-soft)]'
                  )}
                >
                  <p className="truncate text-xs font-medium">{item.title || item.target || '未命名条目'}</p>
                  <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                    {item.source || 'tracking'} · {relativeTime(item.updated_at)}
                  </p>
                  <p className="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-muted)]">{item.preview}</p>
                </button>
              ))}
            </div>
            {!isLoading && items.length === 0 && (
              <div className="px-3 py-10 text-center text-xs text-[var(--color-text-muted)]">暂无日记记录</div>
            )}
          </div>

          <div className="aelin-card min-h-0 overflow-y-auto p-4">
            {!selectedItem && (
              <div className="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
                <BookOpenText size={15} className="mr-2" />
                选择左侧条目查看预览
              </div>
            )}
            {selectedItem && (
              <div className="space-y-3">
                <div>
                  <h2 className="text-sm font-semibold">{fileContent?.title || selectedItem.title || selectedItem.target || '日记条目'}</h2>
                  <p className="text-[11px] text-[var(--color-text-muted)]">
                    {(fileContent?.entry_kind || selectedItem.entry_kind || selectedItem.kind || 'memory')}
                    {' · '}
                    {(fileContent?.source || selectedItem.source || 'tracking')}
                    {' · '}
                    {(fileContent?.topic_path || selectedItem.topic_path || '未分类')}
                    {' · '}
                    {selectedItem.path}
                  </p>
                </div>
                <article className="prose prose-sm max-w-none text-[var(--color-text)] [&_*]:text-[var(--color-text)]">
                  {contentLoading && <p>正在加载全文…</p>}
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {fileContent?.content || selectedItem.preview || '暂无预览内容'}
                  </ReactMarkdown>
                </article>
              </div>
            )}
          </div>
        </div>
      </div>
    </PageScaffold>
  )
}
