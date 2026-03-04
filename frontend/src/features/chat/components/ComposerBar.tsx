import { useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { Send, Square, Camera, Loader2, Paperclip, X } from 'lucide-react'
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
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [isCapturing, setIsCapturing] = useState(false)
  const [isAttaching, setIsAttaching] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const handleSubmit = async () => {
    if (isStreaming) { onStop(); return }
    const textHint = text.trim()
    if (!textHint && pendingFiles.length === 0) return

    if (pendingFiles.length > 0) {
      if (isAttaching || isCapturing) return
      setIsAttaching(true)
      try {
        await onAttachAndSend(pendingFiles, textHint)
        setPendingFiles([])
        setText('')
      } finally {
        setIsAttaching(false)
      }
      return
    }

    onSend(textHint)
    setText('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      void handleSubmit()
    }
  }

  const handleCapture = async () => {
    if (isStreaming || isCapturing || isAttaching || pendingFiles.length > 0) return
    setIsCapturing(true)
    try {
      await onCaptureAndSend(text.trim())
      setText('')
    } finally {
      setIsCapturing(false)
    }
  }

  const handleAttachmentChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (files.length === 0 || isStreaming || isAttaching || isCapturing) return
    setPendingFiles((prev) => [...prev, ...files].slice(0, 10))
  }

  const openAttachmentPicker = () => {
    if (isStreaming || isAttaching || isCapturing) return
    fileInputRef.current?.click()
  }

  const removePendingFile = (indexToRemove: number) => {
    setPendingFiles((prev) => prev.filter((_, index) => index !== indexToRemove))
  }

  const canSend = !!text.trim() || pendingFiles.length > 0

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
            onChange={handleAttachmentChange}
          />

          {pendingFiles.length > 0 && (
            <div className={cn('mb-2.5 flex flex-wrap items-center gap-1.5 max-[500px]:mb-2', isAttaching && 'pointer-events-none opacity-70')}>
              {pendingFiles.map((file, index) => (
                <span
                  key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-2 py-1 text-[11px] text-[var(--color-text)]"
                  title={file.name}
                >
                  <Paperclip size={11} className="shrink-0 text-[var(--color-text-muted)]" />
                  <span className="max-w-[220px] truncate">{file.name}</span>
                  <button
                    type="button"
                    onClick={() => removePendingFile(index)}
                    disabled={isAttaching}
                    className="rounded-full p-0.5 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-text)]"
                    aria-label={`移除附件 ${file.name}`}
                    title="移除附件"
                  >
                    <X size={11} />
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="flex min-w-0 items-center gap-2 max-[500px]:gap-1">
            <button
              type="button"
              onClick={openAttachmentPicker}
              title={isAttaching ? '正在处理附件' : '上传附件'}
              disabled={isStreaming || isAttaching || isCapturing}
              className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
              aria-label={isAttaching ? '正在处理附件' : '上传附件'}
            >
              {isAttaching ? <Loader2 className="animate-spin" size={compact ? 16 : 17} /> : <Paperclip size={compact ? 16 : 17} />}
            </button>

            <button
              type="button"
              onClick={() => void handleCapture()}
              title={pendingFiles.length > 0 ? '请先发送待处理附件' : isCapturing ? '正在截图' : '截图并发送'}
              disabled={isStreaming || isCapturing || isAttaching || pendingFiles.length > 0}
              className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
              aria-label={pendingFiles.length > 0 ? '请先发送待处理附件' : isCapturing ? '正在截图' : '截图并发送'}
            >
              {isCapturing ? <Loader2 className="animate-spin" size={compact ? 16 : 17} /> : <Camera size={compact ? 16 : 17} />}
            </button>

            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isAttaching}
              placeholder={placeholder}
              className={`min-w-0 flex-1 border-none bg-transparent px-1 outline-none placeholder:text-[var(--color-text-muted)] ${compact ? 'h-8 text-[13px] max-[500px]:text-[12px]' : 'h-9 text-[14px]'}`}
              style={{ fontFamily: 'var(--font-body)' }}
            />

            <button
              type="button"
              onClick={() => void handleSubmit()}
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
