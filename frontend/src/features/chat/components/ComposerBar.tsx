import { useEffect, useId, useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { Send, Square, Camera, Loader2, Paperclip, X, Crop, Monitor } from 'lucide-react'
import toast from 'react-hot-toast'
import { cn } from '@/shared/utils/cn'
import { MAX_PENDING_ATTACHMENTS } from '../constants'
import type { AelinAttachmentUploadResponse } from '@/shared/api/types'

interface Props {
  onSend: (text: string) => void
  onCaptureAndSend: (mode: 'fullscreen' | 'region', textHint: string) => Promise<void>
  onUploadAttachments: (files: File[]) => Promise<AelinAttachmentUploadResponse[]>
  onSendWithAttachments: (attachments: AelinAttachmentUploadResponse[], textHint: string) => Promise<void>
  onStop: () => void
  isStreaming: boolean
  compact?: boolean
  placeholder?: string
}

interface UploadingAttachmentItem {
  id: string
  name: string
  mimeType: string
  sizeBytes: number
}

type AttachmentVisual = {
  badgeText: string
  badgeFrom: string
  badgeTo: string
  badgeTextColor: string
  badgeTextClass: string
  previewFrom: string
  previewTo: string
  typeLabel: string
  sizeLabel: string
}

type AttachmentStyleKey = 'word' | 'ppt' | 'excel' | 'pdf' | 'image' | 'text' | 'code' | 'archive' | 'file'

type AttachmentBadgeStyle = {
  text: string
  textClass: string
  badgeFrom: string
  badgeTo: string
  badgeTextColor: string
  previewFrom: string
  previewTo: string
  type: string
}

const ATTACHMENT_BADGE_STYLES: Record<AttachmentStyleKey, AttachmentBadgeStyle> = {
  word: { text: 'W', textClass: 'text-[21px] font-black', badgeFrom: '#2f76f8', badgeTo: '#153eb9', badgeTextColor: '#ffffff', previewFrom: '#53cde8', previewTo: '#2661e8', type: 'Word' },
  ppt: { text: 'P', textClass: 'text-[21px] font-black', badgeFrom: '#ff846b', badgeTo: '#cf3f2b', badgeTextColor: '#ffffff', previewFrom: '#ffb29d', previewTo: '#f1634a', type: 'PPT' },
  excel: { text: 'X', textClass: 'text-[21px] font-black', badgeFrom: '#42bf7e', badgeTo: '#1b7e4c', badgeTextColor: '#ffffff', previewFrom: '#9de8bc', previewTo: '#35a967', type: 'Excel' },
  pdf: { text: 'PDF', textClass: 'text-[9px] font-black tracking-[0.02em]', badgeFrom: '#ff7b62', badgeTo: '#d44a35', badgeTextColor: '#ffffff', previewFrom: '#ffc2b1', previewTo: '#ff6d52', type: 'PDF' },
  image: { text: 'IMG', textClass: 'text-[8px] font-black', badgeFrom: '#8d7de5', badgeTo: '#5a49bd', badgeTextColor: '#ffffff', previewFrom: '#b9cbff', previewTo: '#7e95f4', type: 'Image' },
  text: { text: 'TXT', textClass: 'text-[8px] font-black', badgeFrom: '#7aa8f5', badgeTo: '#3d6fd8', badgeTextColor: '#ffffff', previewFrom: '#c4d9ff', previewTo: '#8eb0ff', type: 'Text' },
  code: { text: '</>', textClass: 'text-[8px] font-black', badgeFrom: '#6fca8c', badgeTo: '#2f8e53', badgeTextColor: '#ffffff', previewFrom: '#b8f0cb', previewTo: '#74cf96', type: 'Code' },
  archive: { text: 'ZIP', textClass: 'text-[8px] font-black', badgeFrom: '#c9a169', badgeTo: '#946535', badgeTextColor: '#ffffff', previewFrom: '#ead0a7', previewTo: '#cb9f63', type: 'Archive' },
  file: { text: 'FILE', textClass: 'text-[7px] font-black tracking-[0.02em]', badgeFrom: '#9ea8ba', badgeTo: '#6a7382', badgeTextColor: '#ffffff', previewFrom: '#e0e5ef', previewTo: '#b3bccd', type: 'File' },
}

const WORD_EXTENSIONS = new Set(['doc', 'docx'])
const PPT_EXTENSIONS = new Set(['ppt', 'pptx'])
const EXCEL_EXTENSIONS = new Set(['xls', 'xlsx'])
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp', 'svg'])
const ARCHIVE_EXTENSIONS = new Set(['zip', 'rar', '7z', 'tar', 'gz'])
const TEXT_EXTENSIONS = new Set(['txt', 'md', 'markdown', 'log', 'csv', 'xml', 'yaml', 'yml', 'json'])
const CODE_EXTENSIONS = new Set(['ts', 'tsx', 'js', 'jsx', 'py', 'java', 'go', 'rs', 'cpp', 'c', 'h'])

const WORD_MIME_TYPES = new Set([
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
])
const PPT_MIME_TYPES = new Set([
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
])
const EXCEL_MIME_TYPES = new Set([
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
])
const ARCHIVE_MIME_TYPES = new Set([
  'application/zip',
  'application/x-zip-compressed',
  'application/x-7z-compressed',
  'application/x-rar-compressed',
  'application/x-tar',
  'application/x-gtar',
  'application/gzip',
  'application/x-gzip',
])
const TEXT_LIKE_MIME_TYPES = new Set([
  'application/json',
  'application/xml',
  'application/yaml',
  'application/x-yaml',
  'application/csv',
])
const CODE_MIME_TYPES = new Set([
  'application/javascript',
  'text/javascript',
  'text/x-typescript',
  'text/x-python',
  'text/x-java',
  'text/x-go',
  'text/x-rust',
  'text/x-c++src',
  'text/x-csrc',
])

function formatAttachmentSize(sizeBytes: number): string {
  const bytes = Number.isFinite(sizeBytes) ? Math.max(0, sizeBytes) : 0
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

function resolveAttachmentVisual(fileName: string, mimeType: string, sizeBytes: number): AttachmentVisual {
  const lowerName = String(fileName || '').toLowerCase()
  const extension = lowerName.includes('.') ? lowerName.split('.').pop() || '' : ''
  const normalizedMime = String(mimeType || '').toLowerCase()
  const isImage = normalizedMime.startsWith('image/') || IMAGE_EXTENSIONS.has(extension)
  let styleKey: AttachmentStyleKey = 'file'

  if (WORD_MIME_TYPES.has(normalizedMime) || WORD_EXTENSIONS.has(extension)) styleKey = 'word'
  else if (PPT_MIME_TYPES.has(normalizedMime) || PPT_EXTENSIONS.has(extension)) styleKey = 'ppt'
  else if (EXCEL_MIME_TYPES.has(normalizedMime) || EXCEL_EXTENSIONS.has(extension)) styleKey = 'excel'
  else if (normalizedMime === 'application/pdf' || extension === 'pdf') styleKey = 'pdf'
  else if (isImage) styleKey = 'image'
  else if (ARCHIVE_MIME_TYPES.has(normalizedMime) || ARCHIVE_EXTENSIONS.has(extension)) styleKey = 'archive'
  else if (CODE_MIME_TYPES.has(normalizedMime) || CODE_EXTENSIONS.has(extension)) styleKey = 'code'
  else if (normalizedMime.startsWith('text/') || TEXT_LIKE_MIME_TYPES.has(normalizedMime) || TEXT_EXTENSIONS.has(extension)) styleKey = 'text'

  const base = ATTACHMENT_BADGE_STYLES[styleKey]
  const typeLabel = extension ? `${base.type} · ${extension.toUpperCase()}` : base.type
  return {
    badgeText: base.text,
    badgeFrom: base.badgeFrom,
    badgeTo: base.badgeTo,
    badgeTextColor: base.badgeTextColor,
    badgeTextClass: base.textClass,
    previewFrom: base.previewFrom,
    previewTo: base.previewTo,
    typeLabel,
    sizeLabel: formatAttachmentSize(sizeBytes),
  }
}

export function ComposerBar({
  onSend,
  onCaptureAndSend,
  onUploadAttachments,
  onSendWithAttachments,
  onStop,
  isStreaming,
  compact = false,
  placeholder = '输入消息…',
}: Props) {
  const [text, setText] = useState('')
  const [pendingAttachments, setPendingAttachments] = useState<AelinAttachmentUploadResponse[]>([])
  const [uploadingAttachments, setUploadingAttachments] = useState<UploadingAttachmentItem[]>([])
  const [isCapturing, setIsCapturing] = useState(false)
  const [isAttaching, setIsAttaching] = useState(false)
  const [captureMenuOpen, setCaptureMenuOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const captureTriggerRef = useRef<HTMLButtonElement | null>(null)
  const captureMenuRef = useRef<HTMLDivElement | null>(null)
  const captureMenuItemRefs = useRef<Array<HTMLButtonElement | null>>([])
  const inFlightUploadBatchesRef = useRef(0)
  const captureMenuId = useId()
  const hasProcessingAttachments = uploadingAttachments.length > 0
  const usedAttachmentSlots = pendingAttachments.length + uploadingAttachments.length
  const captureDisabled = isStreaming || isCapturing || isAttaching || hasProcessingAttachments || pendingAttachments.length > 0

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
    if (hasProcessingAttachments) return
    const textHint = text.trim()
    if (!textHint && pendingAttachments.length === 0) return

    if (pendingAttachments.length > 0) {
      setIsAttaching(true)
      try {
        await onSendWithAttachments(pendingAttachments, textHint)
        setPendingAttachments([])
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
    const availableSlots = MAX_PENDING_ATTACHMENTS - usedAttachmentSlots
    if (availableSlots <= 0) {
      toast(`最多可添加 ${MAX_PENDING_ATTACHMENTS} 个附件`)
      return
    }
    const picked = files.slice(0, availableSlots)
    if (files.length > availableSlots) toast(`最多可添加 ${MAX_PENDING_ATTACHMENTS} 个附件，已忽略 ${files.length - availableSlots} 个`)
    const uploadingItems: UploadingAttachmentItem[] = picked.map((file, index) => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${Date.now()}-${index}`,
      name: file.name || `attachment-${index + 1}`,
      mimeType: String(file.type || ''),
      sizeBytes: Number(file.size || 0),
    }))
    setUploadingAttachments((prev) => [...prev, ...uploadingItems].slice(0, MAX_PENDING_ATTACHMENTS))
    inFlightUploadBatchesRef.current += 1
    setIsAttaching(true)
    void onUploadAttachments(picked)
      .then((uploaded) => {
        setPendingAttachments((prev) => [...prev, ...uploaded].slice(0, MAX_PENDING_ATTACHMENTS))
        if (uploaded.length < picked.length) {
          const uploadedNames = new Set(uploaded.map((item) => String(item.file_name || '').trim()).filter(Boolean))
          const failedNames = picked
            .map((file) => file.name || '')
            .filter((name) => name && !uploadedNames.has(name))
          if (failedNames.length > 0) {
            toast(`部分附件上传失败：${failedNames.join('、')}`)
          }
        }
      })
      .catch((error) => {
        console.error('Attachment upload failed:', error)
      })
      .finally(() => {
        setUploadingAttachments((prev) => prev.filter((row) => !uploadingItems.some((item) => item.id === row.id)))
        inFlightUploadBatchesRef.current = Math.max(0, inFlightUploadBatchesRef.current - 1)
        if (inFlightUploadBatchesRef.current === 0) {
          setIsAttaching(false)
        }
      })
  }

  const openAttachmentPicker = () => {
    if (isStreaming || isAttaching || isCapturing) return
    if (usedAttachmentSlots >= MAX_PENDING_ATTACHMENTS) return
    fileInputRef.current?.click()
  }

  const removePendingAttachment = (indexToRemove: number) => {
    setPendingAttachments((prev) => prev.filter((_, index) => index !== indexToRemove))
  }

  const canSend = !!text.trim() || pendingAttachments.length > 0
  const canSendNow = canSend && !isCapturing && !isAttaching && !hasProcessingAttachments
  const captureButtonLabel = pendingAttachments.length > 0
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
            accept="image/*,.pdf,.txt,.md,.csv,.json,.xml,.yaml,.yml,.log,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.zip,.rar,.7z,.tar,.gz,.ts,.tsx,.js,.jsx,.py,.java,.go,.rs,.cpp,.c,.h"
            onChange={handleAttachmentChange}
          />

          {(uploadingAttachments.length > 0 || pendingAttachments.length > 0) && (
            <div className={cn('mb-2.5 flex items-stretch gap-2 overflow-x-auto pb-1 max-[500px]:mb-2', isAttaching && 'pointer-events-none opacity-70')}>
              {uploadingAttachments.map((attachment) => {
                const visual = resolveAttachmentVisual(attachment.name, attachment.mimeType, attachment.sizeBytes)
                return (
                  <div
                    key={attachment.id}
                    className="flex w-[250px] shrink-0 min-w-0 items-center gap-2 rounded-[14px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-3 py-2"
                    title={attachment.name}
                  >
                    <span
                      className="h-4 w-4 shrink-0 rounded-full border-2 border-[var(--color-border-strong)] border-t-[var(--color-accent)] animate-spin"
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-[var(--color-text)]">{attachment.name}</span>
                      <span className="block text-[11px] text-[var(--color-text-muted)]">上传中 · {visual.typeLabel} · {visual.sizeLabel}</span>
                    </span>
                  </div>
                )
              })}
              {pendingAttachments.map((attachment, index) => {
                const visual = resolveAttachmentVisual(attachment.file_name, attachment.mime_type, attachment.size_bytes)
                return (
                  <div
                    key={`${attachment.attachment_id}-${attachment.file_name}-${index}`}
                    className="group flex w-[280px] shrink-0 min-w-0 items-center gap-2 rounded-[14px] border border-[var(--color-border)] bg-[var(--color-panel-alt)] px-3 py-2"
                    title={attachment.file_name}
                  >
                    <span
                      className="relative inline-flex h-10 w-8 shrink-0"
                      aria-hidden="true"
                    >
                      <span className="absolute inset-0 rounded-[11px] border-2 border-[var(--color-border)] bg-[var(--color-panel)]" />
                      <span
                        className="absolute left-[6px] top-[6px] h-[20px] w-[20px] rounded-[7px]"
                        style={{ backgroundImage: `linear-gradient(135deg, ${visual.previewFrom}, ${visual.previewTo})` }}
                      />
                      <span
                        className="absolute left-[-7px] bottom-[-3px] inline-flex h-[28px] w-[28px] items-center justify-center rounded-[9px] shadow-[0_3px_10px_rgba(13,57,163,0.25)]"
                        style={{ backgroundImage: `linear-gradient(165deg, ${visual.badgeFrom}, ${visual.badgeTo})`, color: visual.badgeTextColor }}
                      >
                        <span className={cn('leading-none', visual.badgeTextClass)}>{visual.badgeText}</span>
                      </span>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium text-[var(--color-text)]">{attachment.file_name}</span>
                      <span className="block text-[12px] text-[var(--color-text-muted)]">{visual.typeLabel} · {visual.sizeLabel}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => removePendingAttachment(index)}
                      disabled={isAttaching}
                      className="shrink-0 rounded-full p-1 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] hover:text-[var(--color-text)]"
                      aria-label={`移除附件 ${attachment.file_name}`}
                      title="移除附件"
                    >
                      <X size={13} />
                    </button>
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex min-w-0 items-center gap-2 max-[500px]:gap-1">
            <button
              type="button"
              onClick={openAttachmentPicker}
              title={
                usedAttachmentSlots >= MAX_PENDING_ATTACHMENTS
                  ? `最多可添加 ${MAX_PENDING_ATTACHMENTS} 个附件`
                  : isAttaching
                    ? '正在处理附件'
                    : '上传附件'
              }
              disabled={isStreaming || isAttaching || isCapturing || usedAttachmentSlots >= MAX_PENDING_ATTACHMENTS}
              className={`flex shrink-0 items-center justify-center rounded-[10px] text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-accent-soft)] active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`}
              aria-label={
                usedAttachmentSlots >= MAX_PENDING_ATTACHMENTS
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
              disabled={isCapturing || isAttaching || hasProcessingAttachments || (!isStreaming && !canSend)}
              className={cn(
                `flex shrink-0 items-center justify-center rounded-[10px] transition-all active:scale-[0.96] ${compact ? 'h-8 w-8' : 'h-9 w-9'}`,
                isStreaming
                  ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                  : canSendNow
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
