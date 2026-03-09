import { formatBytes } from './formatBytes'

export type AttachmentVisual = {
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

const ATTACHMENT_BADGE_STYLES = {
  word: { text: 'W', textClass: 'text-[21px] font-black', badgeFrom: '#2f76f8', badgeTo: '#153eb9', badgeTextColor: '#ffffff', previewFrom: '#53cde8', previewTo: '#2661e8', type: 'Word' },
  ppt: { text: 'P', textClass: 'text-[21px] font-black', badgeFrom: '#ff846b', badgeTo: '#cf3f2b', badgeTextColor: '#ffffff', previewFrom: '#ffb29d', previewTo: '#f1634a', type: 'PPT' },
  excel: { text: 'X', textClass: 'text-[21px] font-black', badgeFrom: '#42bf7e', badgeTo: '#1b7e4c', badgeTextColor: '#ffffff', previewFrom: '#9de8bc', previewTo: '#35a967', type: 'Excel' },
  pdf: { text: 'PDF', textClass: 'text-[9px] font-black tracking-[0.02em]', badgeFrom: '#ff7b62', badgeTo: '#d44a35', badgeTextColor: '#ffffff', previewFrom: '#ffc2b1', previewTo: '#ff6d52', type: 'PDF' },
  image: { text: 'IMG', textClass: 'text-[8px] font-black', badgeFrom: '#8d7de5', badgeTo: '#5a49bd', badgeTextColor: '#ffffff', previewFrom: '#b9cbff', previewTo: '#7e95f4', type: 'Image' },
  text: { text: 'TXT', textClass: 'text-[8px] font-black', badgeFrom: '#7aa8f5', badgeTo: '#3d6fd8', badgeTextColor: '#ffffff', previewFrom: '#c4d9ff', previewTo: '#8eb0ff', type: 'Text' },
  code: { text: '</>', textClass: 'text-[8px] font-black', badgeFrom: '#6fca8c', badgeTo: '#2f8e53', badgeTextColor: '#ffffff', previewFrom: '#b8f0cb', previewTo: '#74cf96', type: 'Code' },
  archive: { text: 'ZIP', textClass: 'text-[8px] font-black', badgeFrom: '#c9a169', badgeTo: '#946535', badgeTextColor: '#ffffff', previewFrom: '#ead0a7', previewTo: '#cb9f63', type: 'Archive' },
  file: { text: 'FILE', textClass: 'text-[7px] font-black tracking-[0.02em]', badgeFrom: '#9ea8ba', badgeTo: '#6a7382', badgeTextColor: '#ffffff', previewFrom: '#e0e5ef', previewTo: '#b3bccd', type: 'File' },
} as const satisfies Record<AttachmentStyleKey, {
  text: string
  textClass: string
  badgeFrom: string
  badgeTo: string
  badgeTextColor: string
  previewFrom: string
  previewTo: string
  type: string
}>

const WORD_EXTENSIONS = new Set(['doc', 'docx'])
const PPT_EXTENSIONS = new Set(['ppt', 'pptx'])
const EXCEL_EXTENSIONS = new Set(['xls', 'xlsx'])
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'bmp', 'gif', 'webp', 'svg'])
const ARCHIVE_EXTENSIONS = new Set(['zip', 'rar', '7z', 'tar', 'gz'])
const TEXT_EXTENSIONS = new Set(['txt', 'md', 'markdown', 'log', 'csv', 'xml', 'yaml', 'yml', 'json'])
const CODE_EXTENSIONS = new Set([
  'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs',
  'py', 'java', 'go', 'rs',
  'c', 'h', 'cc', 'hh', 'cpp', 'hpp', 'cxx', 'hxx',
  'cs', 'rb', 'php', 'swift', 'kt', 'kts',
  'm', 'mm', 'sh', 'bash', 'ps1', 'sql', 'lua', 'r',
])

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
  'application/x-javascript',
  'text/x-c',
  'text/x-c++',
  'text/x-c++hdr',
  'text/x-c++src',
  'text/x-csrc',
  'text/x-csharp',
  'text/x-typescript',
  'text/x-python',
  'text/x-java',
  'text/x-go',
  'text/x-rust',
  'text/x-shellscript',
  'application/x-sh',
  'text/x-php',
  'application/sql',
])

const ACCEPT_FILE_EXTENSIONS = Array.from(
  new Set<string>([
    'pdf',
    ...WORD_EXTENSIONS,
    ...PPT_EXTENSIONS,
    ...EXCEL_EXTENSIONS,
    ...TEXT_EXTENSIONS,
    ...ARCHIVE_EXTENSIONS,
    ...CODE_EXTENSIONS,
  ]),
)

export const ATTACHMENT_ACCEPT_ATTR = ['image/*', ...ACCEPT_FILE_EXTENSIONS.map((ext) => `.${ext}`)].join(',')

export function resolveAttachmentVisual(fileName: string, mimeType: string, sizeBytes: number): AttachmentVisual {
  const lowerName = String(fileName || '').toLowerCase()
  const extension = lowerName.includes('.') ? lowerName.split('.').pop() || '' : ''
  const normalizedMime = String(mimeType || '')
    .split(';')[0]
    .trim()
    .toLowerCase()
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
  const upperExtension = extension.toUpperCase()
  const typeLabel =
    extension && base.type.toUpperCase() !== upperExtension
      ? `${base.type} · ${upperExtension}`
      : base.type
  return {
    badgeText: base.text,
    badgeFrom: base.badgeFrom,
    badgeTo: base.badgeTo,
    badgeTextColor: base.badgeTextColor,
    badgeTextClass: base.textClass,
    previewFrom: base.previewFrom,
    previewTo: base.previewTo,
    typeLabel,
    sizeLabel: formatBytes(sizeBytes),
  }
}

