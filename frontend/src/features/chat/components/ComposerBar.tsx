import { useState, useRef, type ChangeEvent, type KeyboardEvent } from 'react'
import { Send, Square, ImagePlus } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

interface Props {
  onSend: (text: string, images?: { dataUrl: string; name: string }[]) => void
  onStop: () => void
  isStreaming: boolean
  compact?: boolean
  placeholder?: string
}

export function ComposerBar({
  onSend,
  onStop,
  isStreaming,
  compact = false,
  placeholder = '输入消息…',
}: Props) {
  const [text, setText] = useState('')
  const [images, setImages] = useState<{ dataUrl: string; name: string }[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const handleSubmit = () => {
    if (isStreaming) { onStop(); return }
    if (!text.trim() && images.length === 0) return
    onSend(text.trim(), images.length > 0 ? images : undefined)
    setText('')
    setImages([])
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleImage = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []).slice(0, 4 - images.length)
    files.forEach(f => {
      const reader = new FileReader()
      reader.onload = () => setImages(prev => [...prev, { dataUrl: reader.result as string, name: f.name }].slice(0, 4))
      reader.readAsDataURL(f)
    })
    e.target.value = ''
  }

  const canSend = !!text.trim() || images.length > 0

  return (
    <div className={`border-t border-[var(--color-border)] bg-[var(--color-bg)] ${compact ? 'px-2 py-2 max-[500px]:px-1 max-[500px]:py-1.5' : 'px-2.5 py-2.5 sm:px-3 sm:py-3'}`}>
      <div className="mx-auto min-w-0 w-full max-w-[880px]">
        <div className={`aelin-card min-w-0 rounded-[16px] bg-[var(--color-panel)] transition-shadow duration-200 focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_12%,transparent)] ${compact ? 'p-2 max-[500px]:p-1.5' : 'p-2.5'}`}>
          {images.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {images.map((img, i) => (
                <div key={img.dataUrl} className="relative">
                  <img src={img.dataUrl} className="h-14 w-14 rounded-xl object-cover" />
                  <button
                    onClick={() => setImages((prev) => prev.filter((_, j) => j !== i))}
                    className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-accent)] text-[10px] text-[var(--color-bg)]"
                    aria-label="移除图片"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex min-w-0 items-center gap-2 max-[500px]:gap-1">
            <input ref={fileRef} type="file" accept="image/*" multiple onChange={handleImage} className="hidden" />
            <button
              onClick={() => fileRef.current?.click()}
              title="添加图片"
              className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
              aria-label="添加图片"
            >
              <ImagePlus size={compact ? 16 : 17} />
            </button>

            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              className={`min-w-0 flex-1 border-none bg-transparent px-1 outline-none placeholder:text-[var(--color-text-muted)] ${compact ? 'h-8 text-[13px] max-[500px]:text-[12px]' : 'h-9 text-[14px]'}`}
              style={{ fontFamily: 'var(--font-body)' }}
            />

            <button
              onClick={handleSubmit}
              disabled={!isStreaming && !canSend}
              className={cn(
                `flex shrink-0 items-center justify-center rounded-[10px] transition-all active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`,
                isStreaming
                  ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                  : canSend
                    ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                    : 'bg-[var(--color-accent-soft)] text-[var(--color-text-muted)]'
              )}
              aria-label={isStreaming ? '停止生成' : '发送消息'}
            >
              {isStreaming ? <Square size={compact ? 14 : 15} /> : <Send size={compact ? 14 : 15} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
