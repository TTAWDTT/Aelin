import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BookOpenText, ChevronDown, ChevronRight, FileText, Folder, FolderOpen, RefreshCw, Search } from 'lucide-react'
import { aelinApi } from '@/shared/api/aelin'
import { relativeTime } from '@/shared/utils/format'
import { cn } from '@/shared/utils/cn'
import { PageScaffold } from '@/shared/components/PageScaffold'
import type { AelinDiaryTreeNode } from '@/shared/api/types'

const HUMAN_SECTION_RE = /^(提炼信息（日记）|今日对话|Insight|Summary|总结|概要)$/i
const HIDDEN_SECTION_RE = /^(Normalized Payload|Diff|Config|Tags|来源索引)$/i
const HIDDEN_META_RE =
  /^-\s*(canonical_id|target|source|kind|entry_kind|topic_path|created_at|fetched_at|updated_at|confidence|query|reason|source_indices_json|fetch_status|item_count|fetch_error|version)\s*:/i

function filterTree(nodes: AelinDiaryTreeNode[], query: string): AelinDiaryTreeNode[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return nodes

  const walk = (items: AelinDiaryTreeNode[]): AelinDiaryTreeNode[] => {
    const out: AelinDiaryTreeNode[] = []
    for (const item of items) {
      const hit = `${item.name} ${item.title} ${item.preview} ${item.source} ${item.topic_path} ${item.entry_kind}`.toLowerCase().includes(needle)
      if (item.kind === 'folder') {
        const children = walk(item.children || [])
        if (hit || children.length > 0) out.push({ ...item, children })
      } else if (hit) {
        out.push(item)
      }
    }
    return out
  }
  return walk(nodes)
}

function findNodeByPath(nodes: AelinDiaryTreeNode[], path: string): AelinDiaryTreeNode | null {
  for (const node of nodes) {
    if (node.path === path) return node
    if (node.children?.length) {
      const child = findNodeByPath(node.children, path)
      if (child) return child
    }
  }
  return null
}

function findFirstFilePath(nodes: AelinDiaryTreeNode[]): string {
  for (const node of nodes) {
    if (node.kind === 'file') return node.path
    if (node.children?.length) {
      const child = findFirstFilePath(node.children)
      if (child) return child
    }
  }
  return ''
}

function parentFolderPaths(path: string): string[] {
  const parts = path.split('/').filter(Boolean)
  const out: string[] = []
  for (let i = 1; i < parts.length; i += 1) out.push(parts.slice(0, i).join('/'))
  return out
}

function collapseMarkdownNoise(raw: string): string {
  const lines = raw.replace(/\r\n/g, '\n').split('\n')
  const withoutCodeBlocks: string[] = []
  let inCode = false
  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      inCode = !inCode
      continue
    }
    if (!inCode) withoutCodeBlocks.push(line)
  }

  const sections = new Map<string, string[]>()
  let current = ''
  for (const line of withoutCodeBlocks) {
    const h2 = line.match(/^##\s+(.+)$/)
    if (h2) {
      current = h2[1].trim()
      if (!sections.has(current)) sections.set(current, [])
      continue
    }
    if (HIDDEN_META_RE.test(line.trim())) continue
    if (current && !HIDDEN_SECTION_RE.test(current)) {
      sections.get(current)?.push(line)
    }
  }

  const humanSections = [...sections.entries()]
    .filter(([title]) => HUMAN_SECTION_RE.test(title))
    .map(([title, content]) => {
      const cleaned = content
        .map((line) => line.trimEnd())
        .filter((line) => line.trim() && !HIDDEN_META_RE.test(line.trim()))
      return { title, text: cleaned.join('\n').trim() }
    })
    .filter((row) => row.text)

  let merged = ''
  if (humanSections.length > 0) {
    merged = humanSections.map((row) => `## ${row.title}\n\n${row.text}`).join('\n\n')
  } else {
    const cleaned = withoutCodeBlocks
      .map((line) => line.trimEnd())
      .filter((line) => {
        const t = line.trim()
        if (!t) return false
        if (t.startsWith('# Tracking')) return false
        if (t === '# Tracking Snapshot' || t === '# Tracking Change' || t === '# Tracking Profile') return false
        if (HIDDEN_META_RE.test(t)) return false
        if (/^##\s+/.test(t) && HIDDEN_SECTION_RE.test(t.replace(/^##\s+/, '').trim())) return false
        return true
      })
    merged = cleaned.join('\n')
  }

  const dedup: string[] = []
  const seen = new Set<string>()
  for (const line of merged.split('\n')) {
    const key = line.trim().toLowerCase()
    if (key && seen.has(key)) continue
    if (key) seen.add(key)
    dedup.push(line)
  }
  return dedup.join('\n').replace(/\n{3,}/g, '\n\n').trim().slice(0, 3600)
}

type TreeNodeProps = {
  node: AelinDiaryTreeNode
  depth: number
  expanded: Set<string>
  selectedPath: string
  onToggle: (path: string) => void
  onSelect: (path: string) => void
}

function DiaryTreeNodeItem({ node, depth, expanded, selectedPath, onToggle, onSelect }: TreeNodeProps) {
  const isFolder = node.kind === 'folder'
  const isOpen = expanded.has(node.path)
  const isSelected = selectedPath === node.path
  const pad = 10 + depth * 14

  if (isFolder) {
    return (
      <div>
        <button
          onClick={() => onToggle(node.path)}
          className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-xs hover:bg-[var(--color-accent-soft)]"
          style={{ paddingLeft: `${pad}px` }}
        >
          {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          {isOpen ? <FolderOpen size={13} /> : <Folder size={13} />}
          <span className="truncate">{node.name}</span>
        </button>
        {isOpen && (
          <div>
            {node.children?.map((child) => (
              <DiaryTreeNodeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                expanded={expanded}
                selectedPath={selectedPath}
                onToggle={onToggle}
                onSelect={onSelect}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <button
      onClick={() => onSelect(node.path)}
      className={cn(
        'flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-xs hover:bg-[var(--color-accent-soft)]',
        isSelected && 'bg-[var(--color-accent-soft)]'
      )}
      style={{ paddingLeft: `${pad}px` }}
      title={node.title || node.name}
    >
      <FileText size={12} />
      <span className="truncate">{node.title || node.name}</span>
    </button>
  )
}

export function DiaryView() {
  const [query, setQuery] = useState('')
  const [selectedPath, setSelectedPath] = useState<string>('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const { data: tree, isLoading, isFetching, isError, error, refetch } = useQuery({
    queryKey: ['diary-tree'],
    queryFn: () =>
      aelinApi.fileMemoryTree({
        workspace: 'default',
        max_files: '1200',
      }),
  })
  const treeItems = tree?.items ?? []
  const filteredTree = useMemo(() => filterTree(treeItems, query), [treeItems, query])

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
    if (!filteredTree.length) {
      setSelectedPath('')
      return
    }
    if (!selectedPath || !findNodeByPath(filteredTree, selectedPath)) {
      setSelectedPath(findFirstFilePath(filteredTree))
    }
  }, [filteredTree, selectedPath])

  useEffect(() => {
    if (!selectedPath) return
    setExpanded((prev) => {
      const next = new Set(prev)
      for (const path of parentFolderPaths(selectedPath)) next.add(path)
      return next
    })
  }, [selectedPath])

  useEffect(() => {
    if (!treeItems.length) return
    setExpanded((prev) => {
      if (prev.size > 0) return prev
      const next = new Set<string>()
      for (const node of treeItems.slice(0, 2)) {
        if (node.kind === 'folder') next.add(node.path)
      }
      return next
    })
  }, [treeItems])

  const selectedNode = useMemo(() => findNodeByPath(treeItems, selectedPath), [treeItems, selectedPath])
  const humanMarkdown = useMemo(
    () => collapseMarkdownNoise(fileContent?.content || ''),
    [fileContent?.content]
  )
  const mergedPreview = useMemo(() => {
    const preview = (selectedNode?.preview || '').trim()
    if (!preview) return ''
    const headline = `## 摘要\n\n${preview}`
    if (!humanMarkdown) return headline
    return `${headline}\n\n${humanMarkdown}`
  }, [selectedNode?.preview, humanMarkdown])

  const fileCount = tree?.total || 0
  const shownCount = useMemo(() => {
    const walk = (nodes: AelinDiaryTreeNode[]): number =>
      nodes.reduce((sum, n) => sum + (n.kind === 'file' ? 1 : walk(n.children || [])), 0)
    return walk(filteredTree)
  }, [filteredTree])

  const toggleFolder = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  return (
    <PageScaffold title="Aelinの日记" subtitle={`分层树浏览 · ${shownCount}/${fileCount} 条`}>
      <div className="flex h-full min-h-0 flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              className="aelin-input pl-8"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="过滤树节点（标题/路径/来源）"
            />
          </div>
          <button onClick={() => refetch()} className="aelin-btn w-full sm:w-auto" type="button">
            <RefreshCw size={13} className={cn(isFetching && 'animate-spin')} />
            刷新树
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[330px_minmax(0,1fr)]">
          <div className="aelin-card min-h-0 overflow-hidden">
            <div className="border-b border-[var(--color-border)] px-3 py-2 text-[11px] text-[var(--color-text-muted)]">
              日记树可展开/收缩，点击文件查看阅读版内容
            </div>
            <div className="min-h-0 overflow-y-auto p-2">
              {filteredTree.map((node) => (
                <DiaryTreeNodeItem
                  key={node.path}
                  node={node}
                  depth={0}
                  expanded={expanded}
                  selectedPath={selectedPath}
                  onToggle={toggleFolder}
                  onSelect={setSelectedPath}
                />
              ))}
            </div>
            {!isLoading && filteredTree.length === 0 && (
              <div className="px-3 py-8 text-center text-xs text-[var(--color-text-muted)]">当前筛选下没有节点</div>
            )}
            {isError && (
              <div className="px-3 py-4 text-center text-xs text-[var(--color-danger)]">
                日记读取失败：{(error as Error)?.message || 'unknown error'}
              </div>
            )}
          </div>

          <div className="aelin-card min-h-0 overflow-y-auto p-4">
            {!selectedNode && (
              <div className="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
                <BookOpenText size={15} className="mr-2" />
                选择左侧树节点查看内容
              </div>
            )}
            {selectedNode && (
              <div className="space-y-3">
                <div>
                  <h2 className="text-sm font-semibold">{fileContent?.title || selectedNode.title || selectedNode.name || '日记条目'}</h2>
                  <p className="text-[11px] text-[var(--color-text-muted)]">
                    {(fileContent?.entry_kind || selectedNode.entry_kind || selectedNode.kind || 'memory')}
                    {' · '}
                    {(fileContent?.source || selectedNode.source || 'tracking')}
                    {' · '}
                    {(fileContent?.topic_path || selectedNode.topic_path || '未分类')}
                    {' · '}
                    {selectedNode.path}
                  </p>
                  <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                    {relativeTime(fileContent?.updated_at || selectedNode.updated_at)}
                  </p>
                </div>
                <article className="prose prose-sm max-w-none text-[var(--color-text)] [&_*]:text-[var(--color-text)]">
                  {contentLoading && <p>正在加载全文…</p>}
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {mergedPreview || selectedNode.preview || '暂无预览内容'}
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
