import {
  Bot,
  CheckCircle2,
  CircleDashed,
  Hammer,
  Sparkles,
  Workflow,
  Wrench,
  XCircle,
} from 'lucide-react'
import { cn } from '@/shared/utils/cn'

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

export function compactText(value: unknown, max = 220): string {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

export function stableJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value ?? '')
  }
}

export function truncateBlock(value: string, max = 8000): string {
  const text = String(value || '').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max - 1)}…`
}

export function statusIcon(status?: string) {
  const lowered = String(status || '').toLowerCase()
  if (lowered === 'completed' || lowered === 'success') {
    return <CheckCircle2 size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'failed' || lowered === 'error') {
    return <XCircle size={13} className="text-[var(--color-text)]" />
  }
  if (lowered === 'running' || lowered === 'pending' || lowered === 'streaming') {
    return <CircleDashed size={13} className="animate-spin text-[var(--color-text)]" />
  }
  return <Sparkles size={13} className="text-[var(--color-text-muted)]" />
}

export function nodeIcon(kind: string) {
  const lowered = String(kind || '').toLowerCase()
  if (lowered.includes('tool')) return <Hammer size={12} className="text-[var(--color-text)]" />
  if (lowered.includes('model')) return <Bot size={12} className="text-[var(--color-text)]" />
  if (lowered.includes('middleware')) return <Workflow size={12} className="text-[var(--color-text)]" />
  if (lowered.includes('end') || lowered.includes('final')) return <CheckCircle2 size={12} className="text-[var(--color-text)]" />
  return <Wrench size={12} className="text-[var(--color-text)]" />
}

export function tabClassName(active: boolean) {
  return cn(
    'absolute inset-0 overflow-y-auto transition-[opacity,transform] duration-200',
    active
      ? 'pointer-events-auto translate-y-0 opacity-100'
      : 'pointer-events-none translate-y-1 opacity-0',
  )
}
