import { useEffect, useId, useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { Send, Square, Camera, Loader2, Paperclip, X, Crop, Monitor } from 'lucide-react'
import toast from 'react-hot-toast'
import { cn } from '@/shared/utils/cn'
import { MAX_PENDING_ATTACHMENTS } from '../constants'

interface Props {
  onSend: (text: string) => void
  onCaptureAndSend: (mode: 'fullscreen' | 'region', textHint: string) => Promise<void>
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
  const [captureMenuOpen, setCaptureMenuOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const captureTriggerRef = useRef<HTMLButtonElement | null>(null)
  const captureMenuRef = useRef<HTMLDivElement | null>(null)
  const captureMenuItemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const captureMenuId = useId()
  const captureDisabled = isStreaming || isCapturing || isAttaching || pendingFiles.length > 0

  useEffect(() => {
    if (!captureMenuOpen) return
    const onPointerDown = (event: PointerEvent) => {
      const targetNode = event.target as Node | null
      if (targetNode && captureMenuRef.current?.contains(targetNode)) return
      setCaptureMenuOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [captureMenuOpen])

  useEffect(() => {
    if (captureDisabled) {
      setCaptureMenuOpen(false)
    }
  }, [captureDisabled])

  useEffect(() => {
    if (!captureMenuOpen) return
    const rafId = window.requestAnimationFrame(() => {
      captureMenuItemRefs.current[0]?.focus()
    })
    return () => window.cancelAnimationFrame(rafId)
  }, [captureMenuOpen])

  const handleSubmit = async () => {
    if (isAttaching || isCapturing) return
    if (isStreaming) { onStop(); return }
    const textHint = text.trim()
    if (!textHint && pendingFiles.length === 0) return

    if (pendingFiles.length > 0) {
      setIsAttaching(true)
      try {
        await onAttachAndSend(pendingFiles, textHint)
        setPendingFiles([])
        setText('')
      } catch {
        return
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

  const handleCapture = async (mode: 'fullscreen' | 'region') => {
    if (captureDisabled) return
    setCaptureMenuOpen(false)
    setIsCapturing(true)
    try {
      await onCaptureAndSend(mode, text.trim())
      setText('')
    } catch {
      return
    } finally {
      setIsCapturing(false)
      window.requestAnimationFrame(() => {
        captureTriggerRef.current?.focus()
      })
    }
  }

  const openCaptureMenu = () => {
    if (captureDisabled) return
    setCaptureMenuOpen((prev) => !prev)
  }

  const handleCaptureTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (captureDisabled) return
    if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && !captureMenuOpen) {
      event.preventDefault()
      setCaptureMenuOpen(true)
      return
    }
    if (event.key === 'Escape' && captureMenuOpen) {
      event.preventDefault()
      setCaptureMenuOpen(false)
    }
  }

  const handleCaptureMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const menuItems = captureMenuItemRefs.current.filter((item): item is HTMLButtonElement => Boolean(item))
    if (menuItems.length === 0) return

    const currentIndex = menuItems.findIndex((item) => item === document.activeElement)

    if (event.key === 'Escape') {
      event.preventDefault()
      setCaptureMenuOpen(false)
      captureTriggerRef.current?.focus()
      return
    }

    if (event.key === 'Home') {
      event.preventDefault()
      menuItems[0]?.focus()
      return
    }

    if (event.key === 'End') {
      event.preventDefault()
      menuItems[menuItems.length - 1]?.focus()
      return
    }

    if (event.key === 'Tab') {
      setCaptureMenuOpen(false)
      return
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowUp' ? -1 : 1
      const baseIndex = currentIndex >= 0 ? currentIndex : 0
      const nextIndex = (baseIndex + step + menuItems.length) % menuItems.length
      menuItems[nextIndex]?.focus()
    }
  }

  const handleAttachmentChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (files.length === 0 || isStreaming || isAttaching || isCapturing) return
    const availableSlots = MAX_PENDING_ATTACHMENTS - pendingFiles.length
    if (availableSlots <= 0) {
      toast(`最多可添加 ${MAX_PENDING_ATTACHMENTS} 个附件`)
      return
    }
    if (files.length > availableSlots) {
      toast(`最多可添加 ${MAX_PENDING_ATTACHMENTS} 个附件，已忽略 ${files.length - availableSlots} 个`)
    }
    setPendingFiles([...pendingFiles, ...files.slice(0, availableSlots)])
  }

  const openAttachmentPicker = () => {
    if (isStreaming || isAttaching || isCapturing) return
    if (pendingFiles.length >= MAX_PENDING_ATTACHMENTS) return
    fileInputRef.current?.click()
  }

  const removePendingFile = (indexToRemove: number) => {
    setPendingFiles((prev) => prev.filter((_, index) => index !== indexToRemove))
  }

  const canSend = !!text.trim() || pendingFiles.length > 0
  const captureButtonLabel = pendingFiles.length > 0
    ? '请先发送待处理附件'
    : isCapturing
      ? '正在截图'
      : captureMenuOpen
        ? '关闭截图菜单'
        : '打开截图菜单'

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
              title={
                pendingFiles.length >= MAX_PENDING_ATTACHMENTS
                  ? `最多可添加 ${MAX_PENDING_ATTACHMENTS} 个附件`
                  : isAttaching
                    ? '正在处理附件'
                    : '上传附件'
              }
              disabled={isStreaming || isAttaching || isCapturing || pendingFiles.length >= MAX_PENDING_ATTACHMENTS}
              className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
              aria-label={
                pendingFiles.length >= MAX_PENDING_ATTACHMENTS
                  ? `最多可添加 ${MAX_PENDING_ATTACHMENTS} 个附件`
                  : isAttaching
                    ? '正在处理附件'
                    : '上传附件'
              }
            >
              {isAttaching ? <Loader2 className="animate-spin" size={compact ? 16 : 17} /> : <Paperclip size={compact ? 16 : 17} />}
            </button>

            <div ref={captureMenuRef} className="relative shrink-0">
              <button
                ref={captureTriggerRef}
                type="button"
                onClick={openCaptureMenu}
                onKeyDown={handleCaptureTriggerKeyDown}
                title={captureButtonLabel}
                disabled={captureDisabled}
                className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
                aria-label={captureButtonLabel}
                aria-haspopup="menu"
                aria-expanded={captureMenuOpen}
                aria-controls={captureMenuId}
              >
                {isCapturing ? <Loader2 className="animate-spin" size={compact ? 16 : 17} /> : <Camera size={compact ? 16 : 17} />}
              </button>

              {captureMenuOpen && (
                <div
                  id={captureMenuId}
                  role="menu"
                  aria-label="截图菜单"
                  onKeyDown={handleCaptureMenuKeyDown}
                  className="absolute bottom-[calc(100%+8px)] left-0 z-30 flex min-w-[172px] flex-col gap-1 rounded-[12px] border border-[var(--color-border)] bg-[var(--color-panel)] p-1.5 shadow-[0_8px_24px_rgba(0,0,0,0.18)]"
                >
                  <button
                    ref={(node) => {
                      captureMenuItemRefs.current[0] = node
                    }}
                    type="button"
                    onClick={() => void handleCapture('fullscreen')}
                    className="flex items-center gap-2 rounded-[9px] px-2.5 py-2 text-left text-[12px] text-[var(--color-text)] transition-colors hover:bg-[var(--color-accent-soft)]"
                    role="menuitem"
                    aria-label="全屏截图"
                  >
                    <Monitor size={14} className="shrink-0 text-[var(--color-text-muted)]" />
                    <span>全屏截图</span>
                  </button>
                  <button
                    ref={(node) => {
                      captureMenuItemRefs.current[1] = node
                    }}
                    type="button"
                    onClick={() => void handleCapture('region')}
                    className="flex items-center gap-2 rounded-[9px] px-2.5 py-2 text-left text-[12px] text-[var(--color-text)] transition-colors hover:bg-[var(--color-accent-soft)]"
                    role="menuitem"
                    aria-label="自定义截图"
                  >
                    <Crop size={14} className="shrink-0 text-[var(--color-text-muted)]" />
                    <span>自定义截图</span>
                  </button>
                </div>
              )}
            </div>

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
              disabled={isCapturing || isAttaching || (!isStreaming && !canSend)}
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
