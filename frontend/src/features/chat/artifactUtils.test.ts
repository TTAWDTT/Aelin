import { describe, expect, it } from 'vitest'
import { buildMessageArtifactMap, extractArtifactsFromState, extractArtifactsFromToolCalls, sortArtifacts } from './artifactUtils'

describe('artifactUtils', () => {
  it('extracts previewable runtime files from state', () => {
    const artifacts = extractArtifactsFromState({
      messages: [],
      files: {
        '/report.md': {
          content: ['# Report', '', 'Hello'],
          created_at: '2026-03-30T08:00:00Z',
          modified_at: '2026-03-30T08:05:00Z',
        },
        '/poster.png': {
          content: 'data:image/png;base64,ZmFrZQ==',
          created_at: '2026-03-30T08:06:00Z',
        },
      },
    })

    expect(artifacts.get('/report.md')).toEqual(
      expect.objectContaining({
        name: 'report.md',
        displayPath: '/report.md',
        mimeType: 'text/markdown',
        previewKind: 'markdown',
        previewable: true,
      }),
    )
    expect(artifacts.get('/poster.png')).toEqual(
      expect.objectContaining({
        name: 'poster.png',
        mimeType: 'image/png',
        previewKind: 'image-data-url',
        previewable: true,
      }),
    )
  })

  it('sorts artifacts by latest timestamp before filename', () => {
    const artifacts = extractArtifactsFromState({
      messages: [],
      files: {
        '/b.txt': {
          content: 'older',
          modified_at: '2026-03-30T08:05:00Z',
        },
        '/a.txt': {
          content: 'newer',
          modified_at: '2026-03-30T08:06:00Z',
        },
        '/c.txt': {
          content: 'same-time',
          modified_at: '2026-03-30T08:06:00Z',
        },
      },
    })

    expect(sortArtifacts(artifacts.values()).map((artifact) => artifact.name)).toEqual([
      'a.txt',
      'c.txt',
      'b.txt',
    ])
  })

  it('extracts execute artifacts from tool results and maps them to messages', () => {
    const toolCalls = new Map([
      ['m1', [{
        key: 'call-1',
        name: 'execute',
        state: 'completed',
        args: '{"command":"python build.py"}',
        result: '{"artifact_count":1}',
        artifacts: [{
          path: 'D:/Github/Aelin/output/poster.png',
          relativePath: 'output/poster.png',
          name: 'poster.png',
          mimeType: 'image/png',
          sizeBytes: 16,
          previewKind: 'image-data-url',
          content: 'data:image/png;base64,ZmFrZQ==',
        }],
      }]],
    ])

    const artifacts = extractArtifactsFromToolCalls(toolCalls)
    const artifactMap = buildMessageArtifactMap(toolCalls, new Map())

    expect(artifacts.get('D:/Github/Aelin/output/poster.png')).toEqual(
      expect.objectContaining({
        name: 'poster.png',
        displayPath: 'output/poster.png',
        localPath: 'D:/Github/Aelin/output/poster.png',
        previewKind: 'image-data-url',
      }),
    )
    expect(artifactMap.get('m1')).toEqual([
      expect.objectContaining({
        path: 'D:/Github/Aelin/output/poster.png',
        name: 'poster.png',
      }),
    ])
  })
})
