import fs from "node:fs";
import path from "node:path";

import matter from "gray-matter";
import { imageSize } from "image-size";
import { marked } from "marked";

import {
  encodePath,
  escapeHtmlAttribute,
  getDescriptionFromContent,
  getTitleFromContent,
  normalizeDate,
  preprocessObsidianMarkdown,
  sanitizeHtml,
  splitPathAndSuffix,
} from "./markdown-utils";

export type AboutPageData = {
  title: string;
  description: string;
  date: string;
  relPath: string;
  contentHtml: string;
};

const ABOUT_ROOT = path.resolve(process.cwd(), "content", "about");
const ABOUT_ENTRY = path.resolve(ABOUT_ROOT, "about.md");

function resolveAboutRelativePath(
  currentDocPath: string,
  rawPath: string,
): string | null {
  const normalizedInput = rawPath.replace(/\\/g, "/");
  const currentDir = currentDocPath.split("/").slice(0, -1);
  const parts = normalizedInput.startsWith("/")
    ? normalizedInput.slice(1).split("/")
    : [...currentDir, ...normalizedInput.split("/")];
  const safeParts: string[] = [];

  for (const segment of parts) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (!safeParts.length) return null;
      safeParts.pop();
      continue;
    }
    safeParts.push(segment);
  }

  if (!safeParts.length) return null;

  return safeParts.join("/");
}

function resolveAboutHref(href: string, currentDocPath: string): string {
  if (!href) return href;
  if (/^(https?:|mailto:|tel:|#|data:|\/\/)/i.test(href)) return href;

  const { pathname, suffix } = splitPathAndSuffix(href);
  const resolvedPath = resolveAboutRelativePath(currentDocPath, pathname);

  if (!resolvedPath) return href;

  if (/\.(md|mdx)$/i.test(resolvedPath)) {
    return `/about${suffix}`;
  }

  return `/api/about-asset/${encodePath(resolvedPath)}${suffix}`;
}

function resolveImageSrc(src: string, currentDocPath: string): string {
  if (!src) return src;
  if (/^(https?:|data:|\/\/)/i.test(src)) return src;

  const { pathname, suffix } = splitPathAndSuffix(src);
  const resolvedPath = resolveAboutRelativePath(currentDocPath, pathname);

  if (!resolvedPath) return src;

  return `/api/about-asset/${encodePath(resolvedPath)}${suffix}`;
}

function resolveImageAbsolutePath(
  src: string,
  currentDocPath: string,
): string | null {
  if (!src || /^(https?:|data:|\/\/)/i.test(src)) return null;

  const { pathname } = splitPathAndSuffix(src);
  const resolvedPath = resolveAboutRelativePath(currentDocPath, pathname);

  if (!resolvedPath) return null;

  return path.resolve(ABOUT_ROOT, resolvedPath);
}

function renderMarkdownToHtml(
  markdown: string,
  currentDocPath: string,
): string {
  const normalizedMarkdown = preprocessObsidianMarkdown(markdown);
  const renderer = new marked.Renderer();

  renderer.code = ({ text, lang }) => {
    const language = (lang || "").trim();
    const displayLang = language ? language.toUpperCase() : "";
    const langLabel = displayLang
      ? `<span class="docs-code-lang">${escapeHtmlAttribute(displayLang)}</span>`
      : "";

    return [
      `<div class="docs-code-block">`,
      `<div class="docs-code-header">`,
      langLabel,
      `<button class="docs-code-copy" type="button" aria-label="Copy code">Copy</button>`,
      `</div>`,
      `<pre class="docs-code-pre"><code>${text}</code></pre>`,
      `</div>`,
    ].join("");
  };

  renderer.codespan = ({ text }) => {
    return `<code class="docs-inline-code">${text}</code>`;
  };

  renderer.link = ({ href = "", title = null, tokens }) => {
    const resolvedHref = resolveAboutHref(href, currentDocPath);
    const isExternal = /^(https?:|mailto:|tel:|\/\/)/i.test(resolvedHref);
    const text = tokens ? marked.Parser.parseInline(tokens) : "";
    const attrs = [
      `href="${escapeHtmlAttribute(resolvedHref)}"`,
      isExternal ? `target="_blank"` : "",
      isExternal ? `rel="noreferrer noopener"` : "",
      title ? `title="${escapeHtmlAttribute(title)}"` : "",
    ]
      .filter(Boolean)
      .join(" ");

    return `<a ${attrs}>${text}</a>`;
  };

  renderer.image = ({ href = "", text = "", title = null }) => {
    const src = resolveImageSrc(href, currentDocPath);
    const absolutePath = resolveImageAbsolutePath(href, currentDocPath);
    let widthAttr = "";
    let heightAttr = "";

    if (absolutePath && fs.existsSync(absolutePath)) {
      try {
        const dim = imageSize(new Uint8Array(fs.readFileSync(absolutePath)));

        if (dim.width && dim.height) {
          widthAttr = `width="${dim.width}"`;
          heightAttr = `height="${dim.height}"`;
        }
      } catch {
        // ignore image size errors
      }
    }

    const attrs = [
      `src="${escapeHtmlAttribute(src)}"`,
      `alt="${escapeHtmlAttribute(text)}"`,
      widthAttr,
      heightAttr,
      `loading="lazy"`,
      title ? `title="${escapeHtmlAttribute(title)}"` : "",
    ]
      .filter(Boolean)
      .join(" ");

    return `<img class="docs-image" ${attrs} />`;
  };

  const rawHtml = marked.parse(normalizedMarkdown, {
    async: false,
    breaks: false,
    gfm: true,
    renderer,
  }) as string;

  return sanitizeHtml(rawHtml);
}

export function getAboutRootPath(): string {
  return ABOUT_ROOT;
}

export function getAboutPageData(): AboutPageData | null {
  if (!fs.existsSync(ABOUT_ENTRY)) return null;

  const source = fs.readFileSync(ABOUT_ENTRY, "utf8");
  const { data, content } = matter(source);
  const titleFromMeta = typeof data.title === "string" ? data.title.trim() : "";
  const descriptionFromMeta =
    typeof data.description === "string" ? data.description.trim() : "";
  const title = titleFromMeta || getTitleFromContent(content) || "About";
  const description = descriptionFromMeta || getDescriptionFromContent(content);
  const date = normalizeDate(data.date);
  const contentHtml = renderMarkdownToHtml(content, "about.md");

  return {
    title,
    description,
    date,
    relPath: "about.md",
    contentHtml,
  };
}
