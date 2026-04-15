import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const currentDir = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(currentDir, '..', '..')
const globalsCssPath = path.join(projectRoot, 'src', 'styles', 'globals.css')
const publicRoot = path.join(projectRoot, 'public')

describe('global font assets', () => {
  it('keeps every local font declaration backed by a committed file', () => {
    const css = fs.readFileSync(globalsCssPath, 'utf8')
    const fontUrls = Array.from(css.matchAll(/url\((['"]?)(\/fonts\/[^'")]+)\1\)/g), (match) => match[2])

    expect(fontUrls.length).toBeGreaterThan(0)

    for (const fontUrl of fontUrls) {
      const assetPath = path.join(publicRoot, fontUrl.replace(/^\//, ''))
      expect(fs.existsSync(assetPath), `${fontUrl} should exist at ${assetPath}`).toBe(true)
    }
  })
})
