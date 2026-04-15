import { afterEach, describe, expect, it, vi } from 'vitest'
import { createArtifactObjectUrl, fetchArtifactTextContent } from './artifactActions'
import type { ChatArtifact } from './artifactUtils'

function createArtifact(overrides: Partial<ChatArtifact> = {}): ChatArtifact {
  return {
    path: 'D:/Github/Aelin/output/generated-posters/demo/poster.png',
    displayPath: 'output/generated-posters/demo/poster.png',
    name: 'poster.png',
    extension: 'png',
    mimeType: 'image/png',
    sizeBytes: 128,
    content: '',
    relativePath: 'output/generated-posters/demo/poster.png',
    localPath: 'D:/Github/Aelin/output/generated-posters/demo/poster.png',
    previewKind: 'image-data-url',
    previewable: true,
    ...overrides,
  }
}

describe('artifactActions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses local artifact endpoint when previewable file has no inline content', () => {
    const url = createArtifactObjectUrl(createArtifact())

    expect(url).toBe(
      '/api/v1/aelin/artifact/content?path=D%3A%2FGithub%2FAelin%2Foutput%2Fgenerated-posters%2Fdemo%2Fposter.png',
    )
  })

  it('fetches local text preview when inline content is absent', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => '# Preview',
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', { getItem: () => null })

    const content = await fetchArtifactTextContent(createArtifact({
      path: 'D:/Github/Aelin/output/generated-posters/demo/notes.md',
      displayPath: 'output/generated-posters/demo/notes.md',
      name: 'notes.md',
      extension: 'md',
      mimeType: 'text/markdown',
      relativePath: 'output/generated-posters/demo/notes.md',
      localPath: 'D:/Github/Aelin/output/generated-posters/demo/notes.md',
      previewKind: 'markdown',
    }))

    expect(content).toBe('# Preview')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/aelin/artifact/content?path=D%3A%2FGithub%2FAelin%2Foutput%2Fgenerated-posters%2Fdemo%2Fnotes.md',
      expect.objectContaining({
        headers: {},
      }),
    )
  })

  it('builds a blob url from binary image data when no local file path is available', () => {
    const createObjectUrlMock = vi.fn(() => 'blob:artifact-image')
    vi.stubGlobal('URL', {
      createObjectURL: createObjectUrlMock,
      revokeObjectURL: vi.fn(),
    })

    const url = createArtifactObjectUrl(createArtifact({
      path: 'artifact-image.png',
      displayPath: 'artifact-image.png',
      relativePath: undefined,
      localPath: undefined,
      content: '',
      downloadBase64: 'ZmFrZQ==',
      previewKind: 'image-data-url',
    }))

    expect(url).toBe('blob:artifact-image')
    expect(createObjectUrlMock).toHaveBeenCalledTimes(1)
  })
})
