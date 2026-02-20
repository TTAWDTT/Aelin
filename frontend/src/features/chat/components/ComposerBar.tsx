import { useEffect, useState, useRef, type KeyboardEvent } from 'react'
import { Send, Square, ImagePlus } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

const SEARCH_MODES = ['auto', 'local', 'web'] as const
const SEARCH_MODE_LABELS = { auto: '自动', local: '本地', web: '网络' } as const

interface Props {
  onSend: (text: string, images?: { dataUrl: string; name: string }[]) => void
  onStop: () => void
  isStreaming: boolean
  searchMode: 'auto' | 'local' | 'web'
  onSearchModeChange: (v: 'auto' | 'local' | 'web') => void
  variant?: 'docked' | 'hero'
  placeholder?: string
}

export function ComposerBar({
  onSend,
  onStop,
  isStreaming,
  searchMode,
  onSearchModeChange,
  variant = 'docked',
  placeholder = '输入消息…',
}: Props) {
  const [text, setText] = useState('')
  const [images, setImages] = useState<{ dataUrl: string; name: string }[]>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isHero = variant === 'hero'

  const handleSubmit = () => {
    if (isStreaming) { onStop(); return }
    if (!text.trim() && images.length === 0) return
    onSend(text.trim(), images.length > 0 ? images : undefined)
    setText('')
    setImages([])
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []).slice(0, 4 - images.length)
    files.forEach(f => {
      const reader = new FileReader()
      reader.onload = () => setImages(prev => [...prev, { dataUrl: reader.result as string, name: f.name }].slice(0, 4))
      reader.readAsDataURL(f)
    })
    e.target.value = ''
  }

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [text])

  const canSend = !!text.trim() || images.length > 0

  return (
    <div
      className={cn(
        isHero
          ? 'rounded-[28px] border border-[var(--color-border)] bg-[var(--color-panel)] p-3'
          : 'border-t border-[var(--color-border)] bg-[var(--color-panel)] p-3'
      )}
    >
      <div className={cn(isHero ? 'w-full' : 'mx-auto w-full max-w-4xl')}>
      {/* Image preview */}
      {images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {images.map((img, i) => (
            <div key={i} className="relative">
              <img src={img.dataUrl} className="h-14 w-14 rounded-xl object-cover" />
              <button
                onClick={() => setImages(prev => prev.filter((_, j) => j !== i))}
                className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-danger)] text-[10px] text-white"
                aria-label="移除图片"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2.5">
        <input ref={fileRef} type="file" accept="image/*" multiple onChange={handleImage} className="hidden" />
        {!isHero && (
          <button
            onClick={() => fileRef.current?.click()}
            title="添加图片"
            className="shrink-0 rounded-xl p-2 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-strong)]"
            aria-label="添加图片"
          >
            <ImagePlus size={18} />
          </button>
        )}

        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            className={cn(
              'w-full resize-none rounded-2xl px-4 py-2.5 pr-10 text-sm placeholder:text-[var(--color-text-muted)] focus:outline-none',
              isHero
                ? 'border-none bg-transparent'
                : 'border border-[var(--color-border)] bg-[var(--color-bg)] focus:border-[var(--color-border-strong)]'
            )}
            style={{ fontFamily: 'var(--font-body)', maxHeight: '160px', minHeight: '42px' }}
          />
        </div>

        {!isHero && (
          <div className="shrink-0">
            <div className="mb-0.5 px-1 text-[10px] text-[var(--color-text-muted)]">搜索</div>
            <div className="flex overflow-hidden rounded-xl bg-[var(--color-accent-soft)] text-[11px]">
              {SEARCH_MODES.map(m => (
                <button
                  key={m}
                  onClick={() => onSearchModeChange(m)}
                  className={cn(
                    'px-2.5 py-1.5 transition-colors',
                    searchMode === m ? 'bg-[var(--color-accent)] text-[var(--color-bg)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-bg)]'
                  )}
                >
                  {SEARCH_MODE_LABELS[m]}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Send / Stop */}
        <button
          onClick={handleSubmit}
          disabled={!isStreaming && !canSend}
          className={cn(
            'shrink-0 rounded-2xl p-2.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-strong)]',
            isStreaming
              ? 'bg-[var(--color-danger)] text-white'
              : canSend
                ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                : 'bg-[var(--color-accent-soft)] text-[var(--color-text-muted)] cursor-not-allowed'
          )}
          aria-label={isStreaming ? '停止生成' : '发送消息'}
        >
          {isStreaming ? <Square size={16} /> : <Send size={16} />}
        </button>
      </div>

      </div>
    </div>
  )
}
