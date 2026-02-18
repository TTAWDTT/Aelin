import fs from "node:fs/promises";
import path from "node:path";

async function removeIfExists(targetPath) {
  try {
    await fs.rm(targetPath, { recursive: true, force: true });
  } catch {
    // ignore cleanup errors to avoid blocking dev startup
  }
}

const root = process.cwd();
const webpackCachePath = path.join(root, ".next", "cache", "webpack");

await removeIfExists(webpackCachePath);
