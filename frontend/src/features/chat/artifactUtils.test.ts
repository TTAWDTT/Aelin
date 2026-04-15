import { describe, expect, it } from 'vitest'
import {
  artifactFromServerPayload,
  buildMessageArtifactMap,
  extractReferencedArtifactPaths,
  extractArtifactsFromState,
  extractArtifactsFromToolCalls,
  findArtifactsReferencedInText,
  sortArtifacts,
} from './artifactUtils'

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

  it('maps virtual outputs files to local disk paths via runtime capabilities and skips internal runtime files', () => {
    const artifacts = extractArtifactsFromState({
      messages: [],
      files: {
        '/runtime/capabilities.json': {
          content: [
            JSON.stringify({
              workspace_local_path: 'D:/Aelin/output/deepagents/user-1/default/workspace',
              outputs_local_path: 'D:/Aelin/output/deepagents/user-1/default/outputs',
            }),
          ],
        },
        '/outputs/report.docx': {
          content: '',
          modified_at: '2026-03-30T08:07:00Z',
        },
      },
    })

    expect(artifacts.has('/runtime/capabilities.json')).toBe(false)
    expect(artifacts.get('/outputs/report.docx')).toEqual(
      expect.objectContaining({
        name: 'report.docx',
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        previewKind: 'unknown',
        previewable: true,
        localPath: 'D:/Aelin/output/deepagents/user-1/default/outputs/report.docx',
      }),
    )
  })

  it('keeps state-only artifacts unattached until a tool call or explicit reference links them', () => {
    const stateArtifacts = extractArtifactsFromState({
      messages: [],
      files: {
        '/runtime/capabilities.json': {
          content: [
            JSON.stringify({
              outputs_local_path: 'D:/Aelin/output/deepagents/user-1/default/outputs',
            }),
          ],
        },
        '/outputs/orphan-report.pdf': {
          content: '',
          modified_at: '2026-03-30T08:08:00Z',
        },
      },
    })

    expect(buildMessageArtifactMap(new Map(), stateArtifacts)).toEqual(new Map())
  })

  it('finds known artifacts referenced inside assistant message text', () => {
    const artifacts = extractArtifactsFromState({
      messages: [],
      files: {
        '/runtime/capabilities.json': {
          content: [
            JSON.stringify({
              outputs_local_path: 'D:/Aelin/output/deepagents/user-1/default/outputs',
            }),
          ],
        },
        '/outputs/tongji_cherry_blossom_2026_poster.png': {
          content: '',
          modified_at: '2026-03-30T08:07:00Z',
        },
      },
    })

    expect(
      findArtifactsReferencedInText(
        '同济大学海报已生成完成，保存路径：\n`/outputs/tongji_cherry_blossom_2026_poster.png`',
        artifacts,
      ),
    ).toEqual([
      expect.objectContaining({
        path: '/outputs/tongji_cherry_blossom_2026_poster.png',
        localPath: 'D:/Aelin/output/deepagents/user-1/default/outputs/tongji_cherry_blossom_2026_poster.png',
      }),
    ])
  })

  it('extracts referenced artifact paths from markdown text', () => {
    expect(
      extractReferencedArtifactPaths(
        '运行后会保存到 `/outputs/two_people_playing_football.png`，脚本在 `/workspace/generate_football_image.py`',
      ),
    ).toEqual([
      '/outputs/two_people_playing_football.png',
      '/workspace/generate_football_image.py',
    ])
  })

  it('builds a chat artifact from backend resolve payloads', () => {
    expect(
      artifactFromServerPayload({
        path: 'D:/HuaweiMoveData/Users/yixiao/Desktop/Aelin/output/deepagents/user-1/default/outputs/chelsea_poster.png',
        relative_path: 'output/deepagents/user-1/default/outputs/chelsea_poster.png',
        name: 'chelsea_poster.png',
        mime_type: 'image/png',
        size_bytes: 170947,
        preview_kind: 'image-data-url',
        content: '',
        modified_at: '2026-04-15T22:35:00+08:00',
      }),
    ).toEqual(
      expect.objectContaining({
        path: 'D:/HuaweiMoveData/Users/yixiao/Desktop/Aelin/output/deepagents/user-1/default/outputs/chelsea_poster.png',
        localPath: 'D:/HuaweiMoveData/Users/yixiao/Desktop/Aelin/output/deepagents/user-1/default/outputs/chelsea_poster.png',
        displayPath: 'output/deepagents/user-1/default/outputs/chelsea_poster.png',
        previewKind: 'image-data-url',
        previewable: true,
      }),
    )
  })
})
