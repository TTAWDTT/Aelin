import fs from "node:fs";
import path from "node:path";

import matter from "gray-matter";
import { marked } from "marked";

export type DocRecord = {
  relPath: string;
  slug: string[];
  title: string;
  description: string;
  date: string;
  contentHtml: string;
};

export type DocTreeNode =
  | {
      type: "folder";
      name: string;
      key: string;
      children: DocTreeNode[];
    }
  | {
      type: "file";
      name: string;
      key: string;
      relPath: string;
      slug: string[];
      title: string;
    };

type RawDocRecord = Omit<DocRecord, "contentHtml"> & {
  content: string;
};

type DocsSnapshot = {
  docs: DocRecord[];
  slugs: string[][];
  tree: DocTreeNode[];
};

type DocsVersion = {
  fileCount: number;
  maxMtimeMs: number;
};

const DOC_EXTENSIONS = new Set([".md", ".mdx"]);
const FOUNDATION_ROOT = path.resolve(
  process.cwd(),
  "content",
  "docs",
  "aelin-docs-foundation",
);

let cachedSnapshot: DocsSnapshot | null = null;
let cachedVersion: DocsVersion | null = null;

function toPosixPath(filePath: string): string {
  return filePath.replace(/\\/g, "/");
}

function stripDocExtension(filePath: string): string {
  return filePath.replace(/\.(md|mdx)$/i, "");
}

function getTitleFromContent(content: string): string {
  const heading = content.match(/^#\s+(.+)$/m)?.[1]?.trim();

  return heading ?? "";
}

function getDescriptionFromContent(content: string): string {
  const lines = content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines) {
    if (line.startsWith("#")) continue;
    if (line.startsWith("![")) continue;
    if (line.startsWith("---")) continue;
    if (line.startsWith("```")) continue;

    return line.replace(/[*_`>#-]/g, "").trim();
  }

  return "";
}

function normalizeDate(rawDate: unknown): string {
  if (rawDate instanceof Date) {
    return rawDate.toISOString().slice(0, 10);
  }

  if (typeof rawDate === "string") {
    return rawDate;
  }

  return "";
}

function encodePath(pathname: string): string {
  return pathname
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

function toDocHref(slug: string[]): string {
  if (!slug.length) {
    return "/docs";
  }

  return `/docs/${encodePath(slug.join("/"))}`;
}

function splitPathAndSuffix(rawUrl: string): {
  pathname: string;
  suffix: string;
} {
  const queryIndex = rawUrl.indexOf("?");
  const hashIndex = rawUrl.indexOf("#");
  const splitIndex =
    queryIndex === -1
      ? hashIndex
      : hashIndex === -1
        ? queryIndex
        : Math.min(queryIndex, hashIndex);

  if (splitIndex === -1) {
    return { pathname: rawUrl, suffix: "" };
  }

  return {
    pathname: rawUrl.slice(0, splitIndex),
    suffix: rawUrl.slice(splitIndex),
  };
}

function resolveDocsRelativePath(
  currentDocPath: string,
  rawPath: string,
): string | null {
  const normalizedInput = rawPath.replace(/\\/g, "/");
  const currentDir = currentDocPath.split("/").slice(0, -1).join("/");
  const candidate = normalizedInput.startsWith("/")
    ? normalizedInput.slice(1)
    : `${currentDir}/${normalizedInput}`;
  const normalized = candidate
    .split("/")
    .filter((segment) => segment !== ".")
    .reduce<string[]>((parts, segment) => {
      if (!segment) return parts;
      if (segment === "..") {
        parts.pop();
      } else {
        parts.push(segment);
      }

      return parts;
    }, [])
    .join("/");

  if (!normalized || normalized.startsWith("../")) {
    return null;
  }

  return normalized;
}

function resolveMarkdownHref(
  href: string,
  currentDocPath: string,
  docPathSet: Set<string>,
): string {
  if (!href) {
    return href;
  }

  if (/^(https?:|mailto:|tel:|#|data:|\/\/)/i.test(href)) {
    return href;
  }

  const { pathname, suffix } = splitPathAndSuffix(href);

  if (!pathname) {
    return href;
  }

  const resolvedPath = resolveDocsRelativePath(currentDocPath, pathname);

  if (!resolvedPath) {
    return href;
  }

  const extension = [".md", ".mdx"].find((ext) =>
    resolvedPath.toLowerCase().endsWith(ext),
  );

  if (extension) {
    const slug = resolvedPath.slice(0, -extension.length).split("/");

    return `${toDocHref(slug)}${suffix}`;
  }

  if (docPathSet.has(`${resolvedPath}.md`)) {
    return `${toDocHref(resolvedPath.split("/"))}${suffix}`;
  }

  if (docPathSet.has(`${resolvedPath}.mdx`)) {
    return `${toDocHref(resolvedPath.split("/"))}${suffix}`;
  }

  return `/api/docs-asset/${encodePath(resolvedPath)}${suffix}`;
}

function resolveImageSrc(src: string, currentDocPath: string): string {
  if (!src) {
    return src;
  }

  if (/^(https?:|data:|\/\/)/i.test(src)) {
    return src;
  }

  const { pathname, suffix } = splitPathAndSuffix(src);
  const resolvedPath = resolveDocsRelativePath(currentDocPath, pathname);

  if (!resolvedPath) {
    return src;
  }

  return `/api/docs-asset/${encodePath(resolvedPath)}${suffix}`;
}

function escapeHtmlAttribute(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function preprocessObsidianImages(markdown: string): string {
  return markdown.replace(
    /!\[\[([^\]\|]+?)(?:\|([^\]]+))?\]\]/g,
    (_match, rawTarget: string, rawAlt?: string) => {
      const target = rawTarget
        .trim()
        .replace(/\\/g, "/")
        .replace(/^\/+/, "")
        .replace(/^\.\//, "");
      const alt = (rawAlt ?? "").trim();

      return `![${alt}](/${target})`;
    },
  );
}

function renderMarkdownToHtml(
  markdown: string,
  currentDocPath: string,
  docPathSet: Set<string>,
): string {
  const renderer = new marked.Renderer();

  renderer.link = ({ href = "", title = null, tokens }) => {
    const resolvedHref = resolveMarkdownHref(href, currentDocPath, docPathSet);
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
    const attrs = [
      `src="${escapeHtmlAttribute(src)}"`,
      `alt="${escapeHtmlAttribute(text)}"`,
      `loading="lazy"`,
      `decoding="async"`,
      `fetchpriority="low"`,
      title ? `title="${escapeHtmlAttribute(title)}"` : "",
    ]
      .filter(Boolean)
      .join(" ");

    return `<img ${attrs} />`;
  };

  return marked.parse(preprocessObsidianImages(markdown), {
    async: false,
    breaks: false,
    gfm: true,
    renderer,
  }) as string;
}

function readDocsRecursively(rootDir: string, currentDir = ""): RawDocRecord[] {
  const absoluteDir = path.join(rootDir, currentDir);
  const entries = fs
    .readdirSync(absoluteDir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
  const docs: RawDocRecord[] = [];

  for (const entry of entries) {
    const nextRelativePath = toPosixPath(path.join(currentDir, entry.name));

    if (entry.isDirectory()) {
      docs.push(...readDocsRecursively(rootDir, nextRelativePath));
      continue;
    }

    const extension = path.extname(entry.name).toLowerCase();

    if (!DOC_EXTENSIONS.has(extension)) {
      continue;
    }

    const absoluteFilePath = path.join(rootDir, nextRelativePath);
    const source = fs.readFileSync(absoluteFilePath, "utf8");
    const { data, content } = matter(source);
    const fallbackTitle = stripDocExtension(entry.name);
    const titleFromMeta =
      typeof data.title === "string" ? data.title.trim() : "";
    const contentTitle = getTitleFromContent(content);
    const title = titleFromMeta || contentTitle || fallbackTitle;
    const descriptionFromMeta =
      typeof data.description === "string" ? data.description.trim() : "";
    const description =
      descriptionFromMeta || getDescriptionFromContent(content);
    const date = normalizeDate(data.date);
    const relPath = nextRelativePath;
    const slug = stripDocExtension(relPath).split("/");

    docs.push({
      relPath,
      slug,
      title,
      description,
      date,
      content,
    });
  }

  return docs;
}

function sortTree(nodes: DocTreeNode[]): DocTreeNode[] {
  nodes.sort((a, b) => {
    if (a.type !== b.type) {
      return a.type === "folder" ? -1 : 1;
    }

    return a.name.localeCompare(b.name, "zh-CN");
  });

  for (const node of nodes) {
    if (node.type === "folder") {
      node.children = sortTree(node.children);
    }
  }

  return nodes;
}

function computeDocsVersion(rootDir: string, currentDir = ""): DocsVersion {
  const absoluteDir = path.join(rootDir, currentDir);
  const entries = fs.readdirSync(absoluteDir, { withFileTypes: true });
  let fileCount = 0;
  let maxMtimeMs = 0;

  for (const entry of entries) {
    const nextRelativePath = path.join(currentDir, entry.name);

    if (entry.isDirectory()) {
      const childVersion = computeDocsVersion(rootDir, nextRelativePath);
      fileCount += childVersion.fileCount;
      maxMtimeMs = Math.max(maxMtimeMs, childVersion.maxMtimeMs);
      continue;
    }

    const extension = path.extname(entry.name).toLowerCase();

    if (!DOC_EXTENSIONS.has(extension)) {
      continue;
    }

    const absoluteFilePath = path.join(rootDir, nextRelativePath);
    const stat = fs.statSync(absoluteFilePath);

    fileCount += 1;
    maxMtimeMs = Math.max(maxMtimeMs, stat.mtimeMs);
  }

  return {
    fileCount,
    maxMtimeMs,
  };
}

function isSameDocsVersion(left: DocsVersion, right: DocsVersion): boolean {
  return (
    left.fileCount === right.fileCount && left.maxMtimeMs === right.maxMtimeMs
  );
}

function createSnapshot(): DocsSnapshot {
  if (!fs.existsSync(FOUNDATION_ROOT)) {
    return {
      docs: [],
      slugs: [],
      tree: [],
    };
  }

  const rawDocs = readDocsRecursively(FOUNDATION_ROOT).sort((a, b) =>
    a.relPath.localeCompare(b.relPath, "zh-CN"),
  );
  const docPathSet = new Set(rawDocs.map((doc) => doc.relPath));
  const docs: DocRecord[] = rawDocs.map((doc) => ({
    relPath: doc.relPath,
    slug: doc.slug,
    title: doc.title,
    description: doc.description,
    date: doc.date,
    contentHtml: renderMarkdownToHtml(doc.content, doc.relPath, docPathSet),
  }));

  return {
    docs,
    slugs: docs.map((doc) => doc.slug),
    tree: buildDocsTree(docs),
  };
}

function getSnapshot(): DocsSnapshot {
  if (!fs.existsSync(FOUNDATION_ROOT)) {
    cachedSnapshot = {
      docs: [],
      slugs: [],
      tree: [],
    };
    cachedVersion = {
      fileCount: 0,
      maxMtimeMs: 0,
    };

    return cachedSnapshot;
  }

  if (process.env.NODE_ENV === "production") {
    if (!cachedSnapshot) {
      cachedSnapshot = createSnapshot();
    }

    return cachedSnapshot;
  }

  const currentVersion = computeDocsVersion(FOUNDATION_ROOT);

  if (
    cachedSnapshot &&
    cachedVersion &&
    isSameDocsVersion(cachedVersion, currentVersion)
  ) {
    return cachedSnapshot;
  }

  cachedSnapshot = createSnapshot();
  cachedVersion = currentVersion;

  return cachedSnapshot;
}

export function getDocsRootPath(): string {
  return FOUNDATION_ROOT;
}

export function getAllDocs(): DocRecord[] {
  return getSnapshot().docs;
}

export function getAllDocSlugs(): string[][] {
  return getSnapshot().slugs;
}

export function getDocsTree(): DocTreeNode[] {
  return getSnapshot().tree;
}

export function findDocBySlug(
  docs: DocRecord[],
  slug?: string[],
): DocRecord | null {
  if (!docs.length) {
    return null;
  }

  if (slug?.length) {
    const key = slug.join("/");

    return docs.find((doc) => doc.slug.join("/") === key) ?? null;
  }

  const preferred =
    docs.find((doc) => doc.relPath === "getting-started/welcome.md") ??
    docs.find((doc) => doc.relPath.endsWith("/README.md")) ??
    docs[0];

  return preferred ?? null;
}

export function buildDocsTree(docs: DocRecord[]): DocTreeNode[] {
  const root: DocTreeNode[] = [];

  for (const doc of docs) {
    const segments = doc.relPath.split("/");
    const folderSegments = segments.slice(0, -1);
    const fileName = segments[segments.length - 1] ?? doc.title;
    let currentLevel = root;
    let accumulatedPath = "";

    for (const segment of folderSegments) {
      accumulatedPath = accumulatedPath
        ? `${accumulatedPath}/${segment}`
        : segment;
      let folder = currentLevel.find(
        (node) => node.type === "folder" && node.name === segment,
      );

      if (!folder || folder.type !== "folder") {
        folder = {
          type: "folder",
          name: segment,
          key: accumulatedPath,
          children: [],
        };
        currentLevel.push(folder);
      }

      currentLevel = folder.children;
    }

    currentLevel.push({
      type: "file",
      name: fileName,
      key: doc.relPath,
      relPath: doc.relPath,
      slug: doc.slug,
      title: doc.title,
    });
  }

  return sortTree(root);
}
