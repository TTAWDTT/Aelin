import type { GetStaticPaths, GetStaticProps } from "next";

import clsx from "clsx";
import NextLink from "next/link";
import { useMemo } from "react";
import { Link } from "@heroui/link";
import { ScrollShadow } from "@heroui/scroll-shadow";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import DefaultLayout from "@/layouts/default";
import {
  buildDocsTree,
  findDocBySlug,
  getAllDocs,
  getAllDocSlugs,
  type DocRecord,
  type DocTreeNode,
} from "@/lib/docs";

type DocsPageProps = {
  tree: DocTreeNode[];
  currentDoc: DocRecord | null;
  docPaths: string[];
};

const DOC_EXTENSIONS = [".md", ".mdx"];

function encodePath(pathname: string): string {
  return pathname
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

function formatLabel(raw: string): string {
  return raw
    .replace(/\.(md|mdx)$/i, "")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
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

  const extension = DOC_EXTENSIONS.find((ext) =>
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

function DirectoryTree({
  nodes,
  activePath,
}: {
  nodes: DocTreeNode[];
  activePath: string;
}) {
  const folders = nodes.filter((node) => node.type === "folder");
  const files = nodes.filter((node) => node.type === "file");

  return (
    <div className="space-y-3">
      {folders.map((folder) => (
        <div key={folder.key}>
          <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-default-500 dark:text-default-300">
            {formatLabel(folder.name)}
          </p>
          <div className="space-y-1 border-l border-default-200/80 pl-2 dark:border-default-100/20">
            <DirectoryTree activePath={activePath} nodes={folder.children} />
          </div>
        </div>
      ))}
      {files.map((node) => {
        if (node.type !== "file") return null;

        const isActive = node.relPath === activePath;

        return (
          <Link
            key={node.key}
            as={NextLink}
            className={clsx(
              "block rounded-md border-l-2 px-3 py-1.5 text-sm transition-colors",
              isActive
                ? "border-default-900 bg-default-100 font-semibold text-default-900 dark:border-default-100 dark:bg-default-100/10 dark:text-default-50"
                : "border-transparent text-default-700 hover:border-default-400 hover:bg-default-100/70 dark:text-default-200 dark:hover:border-default-500 dark:hover:bg-default-100/5",
            )}
            href={toDocHref(node.slug)}
          >
            {node.title}
          </Link>
        );
      })}
    </div>
  );
}

export default function DocsPage({
  tree,
  currentDoc,
  docPaths,
}: DocsPageProps) {
  const docPathSet = useMemo(() => new Set(docPaths), [docPaths]);

  return (
    <DefaultLayout>
      <section className="docs-shell docs-layout grid w-full grid-cols-1 gap-8 pb-8 pt-2 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-10">
        <aside className="docs-sidebar hidden lg:block lg:sticky lg:top-20 lg:h-[calc(100vh-6rem)]">
          <div className="mb-3 px-2">
            <p className="text-xs font-medium uppercase tracking-[0.1em] text-default-500 dark:text-default-300">
              Aelin Docs
            </p>
          </div>
          <div className="rounded-xl border border-default-200/90 bg-content1/70 p-2 dark:border-default-100/20 dark:bg-default-50/5">
            <ScrollShadow className="h-[calc(100vh-10rem)] px-1 py-1">
              <DirectoryTree
                activePath={currentDoc?.relPath ?? ""}
                nodes={tree}
              />
            </ScrollShadow>
          </div>
        </aside>

        <div className="min-w-0 lg:hidden">
          <details className="rounded-xl border border-default-200/80 bg-content1/70 p-3 dark:border-default-100/20 dark:bg-default-50/5">
            <summary className="cursor-pointer text-sm font-semibold text-default-700 dark:text-default-200">
              浏览文档目录
            </summary>
            <div className="mt-3">
              <ScrollShadow className="max-h-72 pr-1">
                <DirectoryTree
                  activePath={currentDoc?.relPath ?? ""}
                  nodes={tree}
                />
              </ScrollShadow>
            </div>
          </details>
        </div>

        <div className="docs-content min-w-0">
          {currentDoc ? (
            <article className="mx-auto max-w-4xl">
              <header className="border-b border-default-200/80 pb-6 dark:border-default-100/20">
                <p className="mb-2 text-xs font-medium uppercase tracking-[0.08em] text-default-500 dark:text-default-300">
                  {currentDoc.relPath}
                </p>
                <h1 className="text-3xl font-semibold tracking-tight text-default-900 dark:text-default-50 md:text-[2.25rem]">
                  {currentDoc.title}
                </h1>
                {currentDoc.description ? (
                  <p className="mt-3 max-w-3xl text-base text-default-600 dark:text-default-200">
                    {currentDoc.description}
                  </p>
                ) : null}
                {currentDoc.date ? (
                  <p className="mt-3 text-sm text-default-500 dark:text-default-300">
                    Updated {currentDoc.date}
                  </p>
                ) : null}
              </header>
              <div className="pt-6">
                <article className="docs-markdown">
                  <ReactMarkdown
                    components={{
                      a: ({ href = "", children, ...props }) => {
                        const resolvedHref = resolveMarkdownHref(
                          String(href),
                          currentDoc.relPath,
                          docPathSet,
                        );
                        const isExternal = /^(https?:|mailto:|tel:|\/\/)/i.test(
                          resolvedHref,
                        );

                        return (
                          <a
                            {...props}
                            href={resolvedHref}
                            rel={isExternal ? "noreferrer noopener" : undefined}
                            target={isExternal ? "_blank" : undefined}
                          >
                            {children}
                          </a>
                        );
                      },
                      img: ({ src = "", alt = "", ...props }) => (
                        <img
                          {...props}
                          alt={String(alt)}
                          loading="lazy"
                          src={resolveImageSrc(String(src), currentDoc.relPath)}
                        />
                      ),
                    }}
                    remarkPlugins={[remarkGfm]}
                  >
                    {currentDoc.content}
                  </ReactMarkdown>
                </article>
              </div>
            </article>
          ) : (
            <article className="mx-auto max-w-3xl rounded-xl border border-default-200/80 bg-content1/70 p-6 dark:border-default-100/20 dark:bg-default-50/5">
              <h1 className="text-2xl font-semibold tracking-tight text-default-900 dark:text-default-50">
                Docs Not Found
              </h1>
              <p className="mt-3 text-default-600 dark:text-default-300">
                未找到可展示的文档，请确认上一级目录中存在{" "}
                <code>docs/*.md</code> 文件。
              </p>
            </article>
          )}
        </div>
      </section>
    </DefaultLayout>
  );
}

export const getStaticPaths: GetStaticPaths = async () => {
  const slugs = getAllDocSlugs();
  const paths = [{ params: { slug: [] as string[] } }].concat(
    slugs.map((slug) => ({ params: { slug } })),
  );

  return {
    paths,
    fallback: false,
  };
};

export const getStaticProps: GetStaticProps<DocsPageProps> = async ({
  params,
}) => {
  const docs = getAllDocs();
  const tree = buildDocsTree(docs);
  const slugParam = params?.slug;
  const requestedSlug = Array.isArray(slugParam) ? slugParam : [];
  const currentDoc = findDocBySlug(docs, requestedSlug);

  if (!currentDoc && requestedSlug.length > 0) {
    return {
      notFound: true,
    };
  }

  return {
    props: {
      tree,
      currentDoc,
      docPaths: docs.map((doc) => doc.relPath),
    },
  };
};
