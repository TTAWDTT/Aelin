import { describe, expect, it } from 'vitest'
import { createArtifactObjectUrl } from './artifactActions'
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
  it('uses local artifact endpoint when previewable file has no inline content', () => {
    const url = createArtifactObjectUrl(createArtifact())

    expect(url).toBe(
      '/api/v1/aelin/artifact/content?path=D%3A%2FGithub%2FAelin%2Foutput%2Fgenerated-posters%2Fdemo%2Fposter.png',
    )
  })
})
