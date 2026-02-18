import type { NextApiRequest, NextApiResponse } from "next";

import { getDocsSearchEntries, getDocsTree } from "@/lib/docs";

export default function docsManifestHandler(
  _req: NextApiRequest,
  res: NextApiResponse,
) {
  const tree = getDocsTree();
  const searchEntries = getDocsSearchEntries();

  res.setHeader(
    "Cache-Control",
    "public, max-age=300, stale-while-revalidate=1800",
  );
  res.status(200).json({
    searchEntries,
    tree,
  });
}
