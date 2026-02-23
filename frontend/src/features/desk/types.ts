import type { AelinTrackingChangeItem } from '@/shared/api/types'

export type DeskPanelContext = {
  targetId?: number | null
  source?: string | null
  keyword?: string | null
  title?: string | null
}

export type TrackingChangeRow = AelinTrackingChangeItem & {
  target_name: string
  target_source: string
}

export type ChangePreview = {
  title: string
  url: string
  imageUrl: string
}

export type ChangePreviewRow = {
  row: TrackingChangeRow
  preview: ChangePreview
}
