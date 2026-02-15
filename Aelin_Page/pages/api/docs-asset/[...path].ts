import type { NextApiRequest, NextApiResponse } from "next";

import fs from "node:fs";
import path from "node:path";

import { getDocsRootPath } from "@/lib/docs";

const DOCS_ROOT = getDocsRootPath();

const MIME_BY_EXTENSION: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".pdf": "application/pdf",
};

function isPathInside(rootPath: string, targetPath: string): boolean {
  const relative = path.relative(rootPath, targetPath);

  return (
    Boolean(relative) &&
    !relative.startsWith("..") &&
    !path.isAbsolute(relative)
  );
}

export default function docsAssetHandler(
  req: NextApiRequest,
  res: NextApiResponse,
) {
  if (!fs.existsSync(DOCS_ROOT)) {
    res.status(404).json({ message: "docs directory not found" });

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
  const absolutePath = path.resolve(DOCS_ROOT, safeRelativePath);

  if (!isPathInside(DOCS_ROOT, absolutePath)) {
    res.status(400).json({ message: "path out of docs root" });

    return;
  }

  if (!fs.existsSync(absolutePath) || fs.statSync(absolutePath).isDirectory()) {
    res.status(404).json({ message: "asset not found" });

    return;
  }

  const extension = path.extname(absolutePath).toLowerCase();
  const mimeType = MIME_BY_EXTENSION[extension] ?? "application/octet-stream";
  const fileBuffer = fs.readFileSync(absolutePath);

  res.setHeader("Content-Type", mimeType);
  res.setHeader("Cache-Control", "public, max-age=3600");
  res.status(200).send(fileBuffer);
}
