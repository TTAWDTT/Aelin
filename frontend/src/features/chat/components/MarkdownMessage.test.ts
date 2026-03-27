import { describe, expect, it } from 'vitest'
import { normalizeMarkdownContent } from './MarkdownMessage'

describe('MarkdownMessage', () => {
  it('normalizes headings with missing spacing', () => {
    expect(normalizeMarkdownContent('#Title\n##Subtitle')).toBe('# Title\n\n## Subtitle')
  })

  it('separates table blocks so gfm tables can render reliably', () => {
    expect(
      normalizeMarkdownContent('结果如下\n| name | score |\n| --- | --- |\n| Aelin | 100 |\n下一段'),
    ).toContain('结果如下\n\n| name | score |\n| --- | --- |\n| Aelin | 100 |\n\n下一段')
  })
})
