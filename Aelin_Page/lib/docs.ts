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
  slugify,
  splitPathAndSuffix,
  toPosixPath,
} from "./markdown-utils";

export type DocHeading = {
  id: string;
  level: number;
  text: string;
};

export type DocRecord = {
  relPath: string;
  slug: string[];
  title: string;
  description: string;
  date: string;
  contentHtml: string;
  headings: DocHeading[];
};

export type DocSearchEntry = {
  relPath: string;
  slug: string[];
  title: string;
  description: string;
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

type RawDocRecord = Omit<DocRecord, "contentHtml" | "headings"> & {
  content: string;
};

type DocsSnapshot = {
  docs: DocRecord[];
  slugs: string[][];
  tree: DocTreeNode[];
  searchEntries: DocSearchEntry[];
};

type DocsVersion = {
  fileCount: number;
  maxMtimeMs: number;
};

type DocsSnapshotMeta = {
  createdAt: string;
  schemaVersion: number;
  version: DocsVersion;
};

type PersistedDocsSnapshot = DocsSnapshot & {
  __meta?: DocsSnapshotMeta;
};

const DOC_EXTENSIONS = new Set([".md", ".mdx"]);
const SNAPSHOT_SCHEMA_VERSION = 2;
const FOUNDATION_ROOT = path.resolve(
  process.cwd(),
  "content",
  "docs",
  "aelin-docs-foundation",
);
const SNAPSHOT_PATH = path.resolve(
  process.cwd(),
  ".generated",
  "docs-snapshot.json",
);

let cachedSnapshot: DocsSnapshot | null = null;
let cachedVersion: DocsVersion | null = null;

function stripDocExtension(filePath: string): string {
  return filePath.replace(/\.(md|mdx)$/i, "");
}

function toDocHref(slug: string[]): string {
  if (!slug.length) {
    return "/docs";
  }

  return `/docs/${encodePath(slug.join("/"))}`;
}

function resolveDocsRelativePath(
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
      if (!safeParts.length) {
        return null;
      }
      safeParts.pop();
      continue;
    }
    safeParts.push(segment);
  }

  if (!safeParts.length) return null;

  return safeParts.join("/");
}

function resolveMarkdownHref(
  href: string,
  currentDocPath: string,
  docPathSet: Set<string>,
): string {
  if (!href) return href;
  if (/^(https?:|mailto:|tel:|#|data:|\/\/)/i.test(href)) return href;

  const { pathname, suffix } = splitPathAndSuffix(href);

  if (!pathname) return href;

  const resolvedPath = resolveDocsRelativePath(currentDocPath, pathname);

  if (!resolvedPath) return href;

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
  if (!src) return src;
  if (/^(https?:|data:|\/\/)/i.test(src)) return src;

  const { pathname, suffix } = splitPathAndSuffix(src);
  const resolvedPath = resolveDocsRelativePath(currentDocPath, pathname);

  if (!resolvedPath) return src;

  return `/api/docs-asset/${encodePath(resolvedPath)}${suffix}`;
}

function resolveImageAbsolutePath(
  src: string,
  currentDocPath: string,
): string | null {
  if (!src || /^(https?:|data:|\/\/)/i.test(src)) return null;

  const { pathname } = splitPathAndSuffix(src);
  const resolvedPath = resolveDocsRelativePath(currentDocPath, pathname);

  if (!resolvedPath) return null;

  return path.resolve(FOUNDATION_ROOT, resolvedPath);
}

function renderMarkdownToHtml(
  markdown: string,
  currentDocPath: string,
  docPathSet: Set<string>,
): { html: string; headings: DocHeading[] } {
  const normalizedMarkdown = preprocessObsidianMarkdown(markdown, true);
  const renderer = new marked.Renderer();
  const headingCounts = new Map<string, number>();
  const headings: DocHeading[] = [];

  renderer.heading = ({ text, depth }) => {
    const base = slugify(text) || "section";
    const count = headingCounts.get(base) ?? 0;

    headingCounts.set(base, count + 1);
    const id = count ? `${base}-${count}` : base;

    if (depth >= 2 && depth <= 3) {
      headings.push({ id, level: depth, text });
    }

    return `<h${depth} id="${escapeHtmlAttribute(id)}">${text}</h${depth}>`;
  };

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

  return {
    html: sanitizeHtml(rawHtml),
    headings,
  };
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

    if (!DOC_EXTENSIONS.has(extension)) continue;

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

    docs.push({ relPath, slug, title, description, date, content });
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

function createSnapshot(): DocsSnapshot {
  if (!fs.existsSync(FOUNDATION_ROOT)) {
    return { docs: [], slugs: [], tree: [], searchEntries: [] };
  }

  const rawDocs = readDocsRecursively(FOUNDATION_ROOT).sort((a, b) =>
    a.relPath.localeCompare(b.relPath, "zh-CN"),
  );
  const docPathSet = new Set(rawDocs.map((doc) => doc.relPath));

  const docs: DocRecord[] = rawDocs.map((doc) => {
    const rendered = renderMarkdownToHtml(doc.content, doc.relPath, docPathSet);

    return {
      relPath: doc.relPath,
      slug: doc.slug,
      title: doc.title,
      description: doc.description,
      date: doc.date,
      contentHtml: rendered.html,
      headings: rendered.headings,
    };
  });

  return {
    docs,
    slugs: docs.map((doc) => doc.slug),
    tree: buildDocsTree(docs),
    searchEntries: docs.map((doc) => ({
      relPath: doc.relPath,
      slug: doc.slug,
      title: doc.title,
      description: doc.description,
    })),
  };
}

function computeDocsVersion(rootDir: string, currentDir = ""): DocsVersion {
  const absoluteDir = path.join(rootDir, currentDir);
  const entries = fs.readdirSync(absoluteDir, { withFileTypes: true });
  let fileCount = 0;
  let maxMtimeMs = 0;

  for (const entry of entries) {
    const nextRelativePath = path.join(currentDir, entry.name);

    if (entry.isDirectory()) {
      const child = computeDocsVersion(rootDir, nextRelativePath);

      fileCount += child.fileCount;
      maxMtimeMs = Math.max(maxMtimeMs, child.maxMtimeMs);
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

function getPersistedSnapshotMeta(snapshot: PersistedDocsSnapshot): {
  schemaVersion: number;
  version: DocsVersion;
} | null {
  const meta = snapshot.__meta;

  if (!meta) return null;
  if (meta.schemaVersion !== SNAPSHOT_SCHEMA_VERSION) return null;
  if (!meta.version) return null;

  const { fileCount, maxMtimeMs } = meta.version;

  if (!Number.isFinite(fileCount) || !Number.isFinite(maxMtimeMs)) return null;

  return {
    schemaVersion: meta.schemaVersion,
    version: meta.version,
  };
}

function getValidatedSnapshotFromDisk(
  expectedVersion: DocsVersion,
): DocsSnapshot | null {
  if (!fs.existsSync(SNAPSHOT_PATH)) return null;

  try {
    const raw = fs.readFileSync(SNAPSHOT_PATH, "utf8");
    const parsed = JSON.parse(raw) as PersistedDocsSnapshot;
    const meta = getPersistedSnapshotMeta(parsed);

    if (!meta || !isSameDocsVersion(meta.version, expectedVersion)) {
      return null;
    }

    if (!Array.isArray(parsed.docs) || !Array.isArray(parsed.tree)) {
      return null;
    }

    return {
      docs: parsed.docs,
      slugs: Array.isArray(parsed.slugs) ? parsed.slugs : [],
      tree: parsed.tree,
      searchEntries: Array.isArray(parsed.searchEntries)
        ? parsed.searchEntries
        : [],
    };
  } catch {
    return null;
  }
}

function writeSnapshotToDisk(
  snapshot: DocsSnapshot,
  version: DocsVersion,
): void {
  try {
    const dir = path.dirname(SNAPSHOT_PATH);
    const payload: PersistedDocsSnapshot = {
      ...snapshot,
      __meta: {
        createdAt: new Date().toISOString(),
        schemaVersion: SNAPSHOT_SCHEMA_VERSION,
        version,
      },
    };

    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(SNAPSHOT_PATH, JSON.stringify(payload), "utf8");
  } catch {
    // ignore snapshot write errors in runtime
  }
}

function getSnapshot(): DocsSnapshot {
  if (!fs.existsSync(FOUNDATION_ROOT)) {
    cachedSnapshot = { docs: [], slugs: [], tree: [], searchEntries: [] };
    cachedVersion = { fileCount: 0, maxMtimeMs: 0 };

    return cachedSnapshot;
  }

  if (process.env.NODE_ENV !== "production") {
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

  if (!cachedSnapshot) {
    const currentVersion = computeDocsVersion(FOUNDATION_ROOT);
    const diskSnapshot = getValidatedSnapshotFromDisk(currentVersion);

    cachedSnapshot = diskSnapshot;
    cachedVersion = currentVersion;

    if (!cachedSnapshot) {
      cachedSnapshot = createSnapshot();
      writeSnapshotToDisk(cachedSnapshot, currentVersion);
    }
  }

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

export function getDocsSearchEntries(): DocSearchEntry[] {
  return getSnapshot().searchEntries;
}

export function findDocBySlug(
  docs: DocRecord[],
  slug?: string[],
): DocRecord | null {
  if (!docs.length) return null;

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
