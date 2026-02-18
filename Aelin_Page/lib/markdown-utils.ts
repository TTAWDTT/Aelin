/**
 * Shared Markdown / HTML utilities used by both the docs and about
 * content pipelines.  Keeping them in a single module eliminates the
 * code duplication that previously existed across `lib/docs.ts` and
 * `lib/about.ts`.
 */

import DOMPurify from "isomorphic-dompurify";

/* ------------------------------------------------------------------ */
/*  Path helpers                                                      */
/* ------------------------------------------------------------------ */

export function toPosixPath(filePath: string): string {
  return filePath.replace(/\\/g, "/");
}

export function encodePath(pathname: string): string {
  return pathname
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export function splitPathAndSuffix(rawUrl: string): {
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

/* ------------------------------------------------------------------ */
/*  String helpers                                                    */
/* ------------------------------------------------------------------ */

export function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[`~!@#$%^&*()+={}[\]|\\:;"'<>,.?/]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

export function escapeHtmlAttribute(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* ------------------------------------------------------------------ */
/*  Front-matter / content helpers                                    */
/* ------------------------------------------------------------------ */

export function getTitleFromContent(content: string): string {
  const heading = content.match(/^#\s+(.+)$/m)?.[1]?.trim();

  return heading ?? "";
}

export function getDescriptionFromContent(content: string): string {
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

export function normalizeDate(rawDate: unknown): string {
  if (rawDate instanceof Date) {
    return rawDate.toISOString().slice(0, 10);
  }

  if (typeof rawDate === "string") {
    return rawDate;
  }

  return "";
}

/* ------------------------------------------------------------------ */
/*  Obsidian-flavoured Markdown pre-processing                       */
/* ------------------------------------------------------------------ */

/**
 * Convert Obsidian `![[target|alt]]` image embeds into standard
 * Markdown `![alt](target)` syntax before passing to `marked`.
 *
 * @param rootRelative  When `true`, prepend `/` so the target is
 *   resolved from the content root (used by the docs pipeline).
 *   When `false` / omitted the path stays relative (used by about).
 */
export function preprocessObsidianMarkdown(
  markdown: string,
  rootRelative = false,
): string {
  return markdown.replace(
    /!\[\[([^\]\|]+?)(?:\|([^\]]+))?\]\]/g,
    (_match, rawTarget: string, rawAlt?: string) => {
      const target = rawTarget
        .trim()
        .replace(/\\/g, "/")
        .replace(/^\/+/, "")
        .replace(/^\.\//, "");
      const alt = (rawAlt ?? "").trim();

      return rootRelative ? `![${alt}](/${target})` : `![${alt}](${target})`;
    },
  );
}

/* ------------------------------------------------------------------ */
/*  DOMPurify sanitisation                                            */
/* ------------------------------------------------------------------ */

/**
 * Strict allowlist of HTML tags permitted in sanitised Markdown output.
 * Only elements that the `marked` renderer actually produces (plus a
 * few extras for GFM task-lists and the copy-button in code blocks)
 * are allowed.  This replaces the previous `USE_PROFILES: { html: true }`
 * configuration which was overly permissive.
 */
const ALLOWED_TAGS = [
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "p",
  "div",
  "span",
  "br",
  "hr",
  "ul",
  "ol",
  "li",
  "a",
  "strong",
  "b",
  "em",
  "i",
  "del",
  "s",
  "mark",
  "sub",
  "sup",
  "small",
  "abbr",
  "blockquote",
  "pre",
  "code",
  "table",
  "thead",
  "tbody",
  "tfoot",
  "tr",
  "th",
  "td",
  "caption",
  "colgroup",
  "col",
  "img",
  "figure",
  "figcaption",
  "details",
  "summary",
  "dl",
  "dt",
  "dd",
  "input",
  "button",
];

const ALLOWED_ATTR = [
  "href",
  "src",
  "alt",
  "title",
  "id",
  "class",
  "target",
  "rel",
  "width",
  "height",
  "loading",
  "type",
  "aria-label",
  "aria-hidden",
  "colspan",
  "rowspan",
  "scope",
  "checked",
  "disabled",
];

export function sanitizeHtml(rawHtml: string): string {
  return DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
  });
}
