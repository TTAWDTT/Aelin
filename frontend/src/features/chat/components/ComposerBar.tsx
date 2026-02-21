import { useEffect, useState, useRef, type ChangeEvent, type KeyboardEvent } from 'react'
import { Send, Square, ImagePlus } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

interface Props {
  onSend: (text: string, images?: { dataUrl: string; name: string }[]) => void
  onStop: () => void
  isStreaming: boolean
  placeholder?: string
}

export function ComposerBar({
  onSend,
  onStop,
  isStreaming,
  placeholder = '输入消息…',
}: Props) {
  const [text, setText] = useState('')
  const [images, setImages] = useState<{ dataUrl: string; name: string }[]>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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

  const handleImage = (e: ChangeEvent<HTMLInputElement>) => {
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
    <div className="border-t border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-3">
      <div className="mx-auto w-full max-w-[760px]">
        <div className="aelin-card rounded-[16px] bg-[var(--color-panel)] p-2.5">
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

          <div className="flex items-end gap-2">
            <input ref={fileRef} type="file" accept="image/*" multiple onChange={handleImage} className="hidden" />
            <button
              onClick={() => fileRef.current?.click()}
              title="添加图片"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)]"
              aria-label="添加图片"
            >
              <ImagePlus size={17} />
            </button>

            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              rows={1}
              className="aelin-textarea min-h-[40px] flex-1 resize-none border-none bg-transparent px-1 py-1.5"
              style={{ fontFamily: 'var(--font-body)', maxHeight: '160px' }}
            />

            <button
              onClick={handleSubmit}
              disabled={!isStreaming && !canSend}
              className={cn(
                'flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] transition-colors',
                isStreaming
                  ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                  : canSend
                    ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                    : 'bg-[var(--color-accent-soft)] text-[var(--color-text-muted)]'
              )}
              aria-label={isStreaming ? '停止生成' : '发送消息'}
            >
              {isStreaming ? <Square size={15} /> : <Send size={15} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
