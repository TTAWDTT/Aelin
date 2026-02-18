import type { NextApiRequest, NextApiResponse } from "next";

import fs from "node:fs/promises";
import path from "node:path";

import { getAboutRootPath } from "@/lib/about";

const ABOUT_ROOT = getAboutRootPath();

const MIME_BY_EXTENSION: Record<string, string> = {
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".json": "application/json; charset=utf-8",
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".webp": "image/webp",
};

function isPathInside(rootPath: string, targetPath: string): boolean {
  const relative = path.relative(rootPath, targetPath);

  return (
    Boolean(relative) &&
    !relative.startsWith("..") &&
    !path.isAbsolute(relative)
  );
}

export default async function aboutAssetHandler(
  req: NextApiRequest,
  res: NextApiResponse,
) {
  try {
    await fs.access(ABOUT_ROOT);
  } catch {
    res.status(404).json({ message: "about directory not found" });

    return;
  }

  const pathSegments = req.query.path;

  if (!Array.isArray(pathSegments) || pathSegments.length === 0) {
    res.status(400).json({ message: "invalid path" });

    return;
  }

  const safeRelativePath = pathSegments
    .map((segment) => decodeURIComponent(segment))
    .join("/")
    .replace(/\\/g, "/");
  const absolutePath = path.resolve(ABOUT_ROOT, safeRelativePath);

  if (!isPathInside(ABOUT_ROOT, absolutePath)) {
    res.status(400).json({ message: "path out of about root" });

    return;
  }

  let stat: Awaited<ReturnType<typeof fs.stat>>;

  try {
    stat = await fs.stat(absolutePath);
  } catch {
    res.status(404).json({ message: "asset not found" });

    return;
  }

  if (stat.isDirectory()) {
    res.status(404).json({ message: "asset not found" });

    return;
  }

  // Resolve symlinks to prevent path traversal via symlink chains
  const realRoot = await fs.realpath(ABOUT_ROOT);
  const realFile = await fs.realpath(absolutePath);

  if (!isPathInside(realRoot, realFile)) {
    res.status(400).json({ message: "path out of about root" });

    return;
  }

  const extension = path.extname(absolutePath).toLowerCase();
  const mimeType = MIME_BY_EXTENSION[extension] ?? "application/octet-stream";
  const etag = `W/"${stat.size.toString(16)}-${Math.floor(stat.mtimeMs).toString(16)}"`;
  const ifNoneMatch = req.headers["if-none-match"];

  if (ifNoneMatch === etag) {
    res.status(304).end();

    return;
  }

  const fileBuffer = await fs.readFile(absolutePath);

  res.setHeader("Content-Type", mimeType);
  res.setHeader(
    "Cache-Control",
    "public, max-age=86400, stale-while-revalidate=604800",
  );
  res.setHeader("ETag", etag);
  res.setHeader("Last-Modified", stat.mtime.toUTCString());
  res.status(200).send(fileBuffer);
}
