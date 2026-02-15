import fs from "node:fs";
import path from "node:path";

import matter from "gray-matter";

export type DocRecord = {
  relPath: string;
  slug: string[];
  title: string;
  description: string;
  date: string;
  content: string;
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

type DocsSnapshot = {
  docs: DocRecord[];
  slugs: string[][];
  tree: DocTreeNode[];
};

const DOC_EXTENSIONS = new Set([".md", ".mdx"]);
const FOUNDATION_ROOT = path.resolve(
  process.cwd(),
  "content",
  "docs",
  "aelin-docs-foundation",
);

let cachedSnapshot: DocsSnapshot | null = null;

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

function readDocsRecursively(rootDir: string, currentDir = ""): DocRecord[] {
  const absoluteDir = path.join(rootDir, currentDir);
  const entries = fs
    .readdirSync(absoluteDir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
  const docs: DocRecord[] = [];

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

function createSnapshot(): DocsSnapshot {
  if (!fs.existsSync(FOUNDATION_ROOT)) {
    return {
      docs: [],
      slugs: [],
      tree: [],
    };
  }

  const docs = readDocsRecursively(FOUNDATION_ROOT).sort((a, b) =>
    a.relPath.localeCompare(b.relPath, "zh-CN"),
  );

  return {
    docs,
    slugs: docs.map((doc) => doc.slug),
    tree: buildDocsTree(docs),
  };
}

function getSnapshot(): DocsSnapshot {
  if (process.env.NODE_ENV !== "production") {
    return createSnapshot();
  }

  if (!cachedSnapshot) {
    cachedSnapshot = createSnapshot();
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

