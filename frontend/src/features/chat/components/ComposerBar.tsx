import { useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { Send, Square, Camera, Loader2, Paperclip } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

interface Props {
  onSend: (text: string) => void
  onCaptureAndSend: (textHint: string) => Promise<void>
  onAttachAndSend: (files: File[], textHint: string) => Promise<void>
  onStop: () => void
  isStreaming: boolean
  compact?: boolean
  placeholder?: string
}

export function ComposerBar({
  onSend,
  onCaptureAndSend,
  onAttachAndSend,
  onStop,
  isStreaming,
  compact = false,
  placeholder = '输入消息…',
}: Props) {
  const [text, setText] = useState('')
  const [isCapturing, setIsCapturing] = useState(false)
  const [isAttaching, setIsAttaching] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const handleSubmit = () => {
    if (isStreaming) { onStop(); return }
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleCapture = async () => {
    if (isStreaming || isCapturing) return
    setIsCapturing(true)
    try {
      await onCaptureAndSend(text.trim())
      setText('')
    } finally {
      setIsCapturing(false)
    }
  }

  const handleAttachmentChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (files.length === 0 || isStreaming || isAttaching) return
    setIsAttaching(true)
    try {
      await onAttachAndSend(files, text.trim())
      setText('')
    } finally {
      setIsAttaching(false)
    }
  }

  const openAttachmentPicker = () => {
    if (isStreaming || isAttaching) return
    fileInputRef.current?.click()
  }

  const canSend = !!text.trim()

  return (
    <div className={`border-t border-[var(--color-border)] bg-[var(--color-bg)] ${compact ? 'px-2 py-2 max-[500px]:px-1 max-[500px]:py-1.5' : 'px-2.5 py-2.5 sm:px-3 sm:py-3'}`}>
      <div className="mx-auto min-w-0 w-full max-w-[880px]">
        <div className={`aelin-card min-w-0 rounded-[16px] bg-[var(--color-panel)] transition-shadow duration-200 focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-accent)_12%,transparent)] ${compact ? 'p-2 max-[500px]:p-1.5' : 'p-2.5'}`}>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept="image/*,.pdf,.txt,.md,.csv,.json,.xml,.yaml,.yml,.log,.doc,.docx,.ppt,.pptx,.xls,.xlsx"
            onChange={(e) => { void handleAttachmentChange(e) }}
          />

          <div className="flex min-w-0 items-center gap-2 max-[500px]:gap-1">
            <button
              onClick={openAttachmentPicker}
              title={isAttaching ? '正在处理附件' : '上传附件'}
              disabled={isStreaming || isAttaching}
              className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
              aria-label={isAttaching ? '正在处理附件' : '上传附件'}
            >
              {isAttaching ? <Loader2 className="animate-spin" size={compact ? 16 : 17} /> : <Paperclip size={compact ? 16 : 17} />}
            </button>

            <button
              onClick={() => void handleCapture()}
              title={isCapturing ? '正在截图' : '截图并发送'}
              disabled={isStreaming || isCapturing}
              className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
              aria-label={isCapturing ? '正在截图' : '截图并发送'}
            >
              {isCapturing ? <Loader2 className="animate-spin" size={compact ? 16 : 17} /> : <Camera size={compact ? 16 : 17} />}
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
              disabled={!isStreaming && (!canSend || isCapturing || isAttaching)}
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
