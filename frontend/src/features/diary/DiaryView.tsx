import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BookOpenText, CalendarDays, RefreshCw, Search } from 'lucide-react'
import { aelinApi } from '@/shared/api/aelin'
import { relativeTime } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { PageScaffold } from '@/shared/components/PageScaffold'
import type { AelinDiaryTreeNode } from '@/shared/api/types'

const HIDDEN_META_RE =
  /^-\s*(canonical_id|target|source|kind|entry_kind|topic_path|created_at|fetched_at|updated_at|confidence|query|reason|source_indices_json|fetch_status|item_count|fetch_error|version)\s*:/i

type DiaryListItem = {
  path: string
  title: string
  preview: string
  updatedAt: string
  source: string
  entryKind: string
  dateKey: string
  dayLabel: string
  kind: 'daily' | 'raw' | 'legacy'
}

function flattenFiles(nodes: AelinDiaryTreeNode[]): AelinDiaryTreeNode[] {
  const out: AelinDiaryTreeNode[] = []
  const walk = (items: AelinDiaryTreeNode[]) => {
    for (const item of items) {
      if (item.kind === 'file') {
        out.push(item)
        continue
      }
      if (item.children?.length) walk(item.children)
    }
  }
  walk(nodes)
  return out
}

function extractDateKey(path: string, updatedAt: string): string {
  const direct = path.match(/(\d{4}-\d{2}-\d{2})\.md$/)
  if (direct?.[1]) return direct[1]
  const nested = path.match(/\/(\d{4})\/(\d{2})\/(\d{2})(?:\/|$)/)
  if (nested?.[1] && nested?.[2] && nested?.[3]) return `${nested[1]}-${nested[2]}-${nested[3]}`
  const fromUpdated = (updatedAt || '').trim().slice(0, 10)
  if (/^\d{4}-\d{2}-\d{2}$/.test(fromUpdated)) return fromUpdated
  return 'unknown'
}

function buildDiaryList(nodes: AelinDiaryTreeNode[]): DiaryListItem[] {
  const files = flattenFiles(nodes)
  const rows: DiaryListItem[] = files.map((item) => {
    const path = String(item.path || '')
    const entryKind = String(item.entry_kind || '')
    const dateKey = extractDateKey(path, item.updated_at || '')
    const isDaily = /\/daily\//i.test(path) || entryKind === 'chat_diary_daily'
    const isRaw = /\/raw\//i.test(path) || entryKind === 'chat_diary'
    return {
      path,
      title: String(item.title || item.name || '日记'),
      preview: String(item.preview || ''),
      updatedAt: String(item.updated_at || ''),
      source: String(item.source || ''),
      entryKind,
      dateKey,
      dayLabel: dateKey === 'unknown' ? '未标注日期' : dateKey,
      kind: isDaily ? 'daily' : isRaw ? 'raw' : 'legacy',
    }
  })

  rows.sort((a, b) => {
    const ad = Date.parse(a.updatedAt || '')
    const bd = Date.parse(b.updatedAt || '')
    if (Number.isFinite(ad) && Number.isFinite(bd) && ad !== bd) return bd - ad
    return b.path.localeCompare(a.path)
  })

  const dailyByDate = new Map<string, DiaryListItem>()
  const leftovers: DiaryListItem[] = []
  for (const row of rows) {
    if (row.kind !== 'daily') {
      leftovers.push(row)
      continue
    }
    const prev = dailyByDate.get(row.dateKey)
    if (!prev) {
      dailyByDate.set(row.dateKey, row)
      continue
    }
    const prevTs = Date.parse(prev.updatedAt || '')
    const rowTs = Date.parse(row.updatedAt || '')
    if ((Number.isFinite(rowTs) ? rowTs : 0) > (Number.isFinite(prevTs) ? prevTs : 0)) {
      dailyByDate.set(row.dateKey, row)
    }
  }
  return [...dailyByDate.values(), ...leftovers].sort((a, b) => {
    if (a.dateKey !== b.dateKey) return b.dateKey.localeCompare(a.dateKey)
    const ad = Date.parse(a.updatedAt || '')
    const bd = Date.parse(b.updatedAt || '')
    if (Number.isFinite(ad) && Number.isFinite(bd) && ad !== bd) return bd - ad
    return b.path.localeCompare(a.path)
  })
}

function filterEntries(items: DiaryListItem[], query: string): DiaryListItem[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return items
  return items.filter((item) =>
    `${item.title} ${item.preview} ${item.path} ${item.dayLabel} ${item.entryKind}`.toLowerCase().includes(needle)
  )
}

function collapseMarkdownNoise(raw: string): string {
  const lines = raw.replace(/\r\n/g, '\n').split('\n')
  const out: string[] = []
  let inCode = false
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('```')) {
      inCode = !inCode
      continue
    }
    if (inCode) continue
    if (HIDDEN_META_RE.test(trimmed)) continue
    out.push(line)
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim().slice(0, 7000)
}

export function DiaryView() {
  const [query, setQuery] = useState('')
  const [selectedPath, setSelectedPath] = useState('')

  const { data: tree, isLoading, isFetching, isError, error, refetch } = useQuery({
    queryKey: ['diary-tree'],
    queryFn: () =>
      aelinApi.fileMemoryTree({
        workspace: 'default',
        max_files: '2000',
      }),
  })

  const entries = useMemo(() => buildDiaryList(tree?.items || []), [tree?.items])
  const filteredEntries = useMemo(() => filterEntries(entries, query), [entries, query])

  useEffect(() => {
    if (!filteredEntries.length) {
      setSelectedPath('')
      return
    }
    if (!selectedPath || !filteredEntries.some((it) => it.path === selectedPath)) {
      setSelectedPath(filteredEntries[0].path)
    }
  }, [filteredEntries, selectedPath])

  const selectedEntry = useMemo(
    () => filteredEntries.find((it) => it.path === selectedPath) || entries.find((it) => it.path === selectedPath) || null,
    [entries, filteredEntries, selectedPath]
  )

  const { data: fileContent, isLoading: contentLoading } = useQuery({
    queryKey: ['diary-file-content', selectedPath],
    queryFn: () =>
      aelinApi.fileMemoryContent({
        workspace: 'default',
        path: selectedPath,
      }),
    enabled: Boolean(selectedPath),
  })

  const readableMarkdown = useMemo(() => collapseMarkdownNoise(fileContent?.content || ''), [fileContent?.content])

  return (
    <PageScaffold title="Aelinの日记" subtitle={`按日期查看 · ${filteredEntries.length}/${entries.length} 条`}>
      <div className="flex h-full min-h-0 flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              className="aelin-input pl-8"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索日期/标题/内容预览"
            />
          </div>
          <button onClick={() => refetch()} className="aelin-btn w-full sm:w-auto" type="button">
            <RefreshCw size={13} className={cn(isFetching && 'animate-spin')} />
            刷新
          </button>
        </div>

        <div className="grid h-[min(76vh,calc(100vh-210px))] min-h-[540px] min-w-0 grid-cols-1 gap-3 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="aelin-card min-h-0 overflow-hidden">
            <div className="border-b border-[var(--color-border)] px-3 py-2 text-[11px] text-[var(--color-text-muted)]">
              左侧是日记列表（可滚动），优先展示每天汇总；未汇总当天显示原子记录
            </div>
            <div className="h-full min-h-0 overflow-y-auto p-2">
              {filteredEntries.map((entry) => (
                <button
                  key={entry.path}
                  onClick={() => setSelectedPath(entry.path)}
                  className={cn(
                    'mb-1 w-full rounded px-2 py-2 text-left text-xs hover:bg-[var(--color-accent-soft)]',
                    selectedPath === entry.path && 'bg-[var(--color-accent-soft)]'
                  )}
                  title={entry.path}
                >
                  <div className="flex items-center gap-1 text-[10px] text-[var(--color-text-muted)]">
                    <CalendarDays size={11} />
                    <span>{entry.dayLabel}</span>
                    <span>·</span>
                    <span>{entry.kind === 'daily' ? '日汇总' : entry.kind === 'raw' ? '当日记录' : '历史记录'}</span>
                  </div>
                  <div className="mt-1 truncate font-medium text-[var(--color-text)]">{entry.title || '日记'}</div>
                  {entry.preview && (
                    <div className="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-muted)]">{entry.preview}</div>
                  )}
                </button>
              ))}
              {!isLoading && filteredEntries.length === 0 && (
                <div className="px-3 py-8 text-center text-xs text-[var(--color-text-muted)]">没有可显示的日记</div>
              )}
              {isError && (
                <div className="px-3 py-4 text-center text-xs text-[var(--color-danger)]">
                  日记读取失败：{(error as Error)?.message || 'unknown error'}
                </div>
              )}
            </div>
          </div>

          <div className="aelin-card min-h-0 overflow-hidden">
            {!selectedEntry && (
              <div className="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
                <BookOpenText size={15} className="mr-2" />
                选择一条日记查看全文
              </div>
            )}
            {selectedEntry && (
              <div className="flex h-full min-h-0 flex-col">
                <div className="border-b border-[var(--color-border)] px-4 py-3">
                  <h2 className="text-sm font-semibold">{fileContent?.title || selectedEntry.title || '日记'}</h2>
                  <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                    {selectedEntry.dayLabel} · {selectedEntry.kind === 'daily' ? '日汇总' : selectedEntry.kind === 'raw' ? '当日记录' : '历史记录'} ·{' '}
                    {relativeTime(fileContent?.updated_at || selectedEntry.updatedAt)}
                  </p>
                </div>
                <div className="h-full min-h-0 overflow-y-auto p-4">
                  <article className="prose prose-sm max-w-none text-[var(--color-text)] [&_*]:text-[var(--color-text)]">
                    {contentLoading && <p>正在加载全文…</p>}
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {readableMarkdown || selectedEntry.preview || '暂无内容'}
                    </ReactMarkdown>
                  </article>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </PageScaffold>
  )
}
