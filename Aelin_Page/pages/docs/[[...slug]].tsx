import type { GetStaticPaths, GetStaticProps } from "next";

import clsx from "clsx";
import Head from "next/head";
import NextLink from "next/link";
import {
  memo,
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Button } from "@heroui/button";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
} from "@heroui/drawer";
import { Link } from "@heroui/link";
import { ScrollShadow } from "@heroui/scroll-shadow";
import { Tab, Tabs } from "@heroui/tabs";
import { useDisclosure } from "@heroui/use-disclosure";
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
const SIDEBAR_WIDTH_EXPANDED_PX = 280;
const SIDEBAR_WIDTH_COLLAPSED_PX = 56;
const TOP_OFFSET_PX = 56;
const ROOT_TAB_KEY = "__root__";

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

function titleCase(label: string): string {
  return label
    .split(" ")
    .map((chunk) =>
      chunk.length ? `${chunk[0].toUpperCase()}${chunk.slice(1)}` : chunk,
    )
    .join(" ");
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

const DirectoryTree = memo(function DirectoryTree({
  nodes,
  activePath,
  onNavigate,
}: {
  nodes: DocTreeNode[];
  activePath: string;
  onNavigate?: () => void;
}) {
  const folders = nodes.filter((node) => node.type === "folder");
  const files = nodes.filter((node) => node.type === "file");

  return (
    <div className="space-y-3">
      {folders.map((folder) => (
        <div key={folder.key}>
          <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-600 dark:text-zinc-100">
            {titleCase(formatLabel(folder.name))}
          </p>
          <div className="space-y-1 pl-2">
            <DirectoryTree
              activePath={activePath}
              nodes={folder.children}
              onNavigate={onNavigate}
            />
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
              "block rounded-md px-3 py-1.5 text-sm transition-colors",
              isActive
                ? "bg-zinc-100 font-semibold text-zinc-950 dark:bg-white/10 dark:text-white"
                : "text-zinc-700 hover:bg-zinc-100/70 dark:text-zinc-50 dark:hover:bg-white/5",
            )}
            href={toDocHref(node.slug)}
            onPress={onNavigate}
          >
            {node.title}
          </Link>
        );
      })}
    </div>
  );
});

const DocContent = memo(function DocContent({
  currentDoc,
  docPathSet,
}: {
  currentDoc: DocRecord;
  docPathSet: Set<string>;
}) {
  return (
    <article className="mx-auto max-w-4xl">
      <header className="border-b border-zinc-200/80 pb-5 dark:border-white/10">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.08em] text-zinc-600 dark:text-zinc-100">
          {currentDoc.relPath}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white md:text-[2.25rem]">
          {currentDoc.title}
        </h1>
        {currentDoc.description ? (
          <p className="mt-3 max-w-3xl text-base text-zinc-700 dark:text-zinc-50">
            {currentDoc.description}
          </p>
        ) : null}
        {currentDoc.date ? (
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-100">
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
  );
});

export default function DocsPage({
  tree,
  currentDoc,
  docPaths,
}: DocsPageProps) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [selectedTabKey, setSelectedTabKey] = useState<string>(ROOT_TAB_KEY);
  const mobileNav = useDisclosure();

  const docPathSet = useMemo(() => new Set(docPaths), [docPaths]);
  const sidebarWidth = isSidebarCollapsed
    ? SIDEBAR_WIDTH_COLLAPSED_PX
    : SIDEBAR_WIDTH_EXPANDED_PX;

  const onToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const topLevelFolders = useMemo(
    () =>
      tree.filter((node) => node.type === "folder") as Extract<
        DocTreeNode,
        { type: "folder" }
      >[],
    [tree],
  );

  const rootFiles = useMemo(
    () =>
      tree.filter((node) => node.type === "file") as Extract<
        DocTreeNode,
        { type: "file" }
      >[],
    [tree],
  );

  const availableTabs = useMemo(() => {
    const tabs: { key: string; title: string }[] = [];

    if (rootFiles.length) {
      tabs.push({ key: ROOT_TAB_KEY, title: "Overview" });
    }

    for (const folder of topLevelFolders) {
      tabs.push({
        key: folder.name,
        title: titleCase(formatLabel(folder.name)),
      });
    }

    return tabs.length ? tabs : [{ key: ROOT_TAB_KEY, title: "Docs" }];
  }, [rootFiles.length, topLevelFolders]);

  const activeDocTabKey = useMemo(() => {
    const relPath = currentDoc?.relPath ?? "";
    const firstSegment = relPath.split("/")[0] ?? "";

    if (
      firstSegment &&
      topLevelFolders.some((folder) => folder.name === firstSegment)
    ) {
      return firstSegment;
    }

    return availableTabs[0]?.key ?? ROOT_TAB_KEY;
  }, [availableTabs, currentDoc?.relPath, topLevelFolders]);

  useEffect(() => {
    setSelectedTabKey(activeDocTabKey);
  }, [activeDocTabKey]);

  const getNodesForTabKey = useCallback(
    (key: string): DocTreeNode[] => {
      if (key === ROOT_TAB_KEY) {
        return rootFiles;
      }

      const match = topLevelFolders.find((folder) => folder.name === key);

      return match?.children ?? tree;
    },
    [rootFiles, topLevelFolders, tree],
  );

  const tabsClassNames = useMemo(
    () =>
      ({
        tabList:
          "w-full gap-1 rounded-lg bg-transparent p-0 border-b border-zinc-200/80 dark:border-white/10",
        tab: "h-8 px-2 text-xs font-medium text-zinc-700 data-[selected=true]:text-zinc-950 dark:text-zinc-50 dark:data-[selected=true]:text-white",
        cursor: "bg-zinc-950 dark:bg-white",
        panel: "pt-3",
      }) as const,
    [],
  );

  return (
    <DefaultLayout>
      <Head>
        <title>Aelin</title>
      </Head>
      <section
        className="docs-shell docs-layout w-full pb-10 pt-0"
        style={
          {
            "--docs-sidebar-w": `${sidebarWidth}px`,
            "--docs-top": `${TOP_OFFSET_PX}px`,
          } as CSSProperties
        }
      >
        <aside className="docs-sidebar-fixed hidden lg:block">
          <div className="flex items-center justify-between px-2">
            {!isSidebarCollapsed ? (
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-700 dark:text-white">
                Aelin
              </p>
            ) : (
              <span aria-hidden="true" />
            )}
            <Button
              aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              className="min-w-0"
              isIconOnly
              size="sm"
              variant="light"
              onPress={onToggleSidebar}
            >
              <span className="text-sm font-semibold text-zinc-700 dark:text-white">
                {isSidebarCollapsed ? ">" : "<"}
              </span>
            </Button>
          </div>
          <div className="mt-3">
            {!isSidebarCollapsed ? (
              <Tabs
                aria-label="Docs sections"
                classNames={tabsClassNames}
                color="default"
                radius="md"
                selectedKey={selectedTabKey}
                size="sm"
                variant="underlined"
                onSelectionChange={(key) => setSelectedTabKey(String(key))}
              >
                {availableTabs.map((tab) => (
                  <Tab key={tab.key} title={tab.title}>
                    <ScrollShadow className="docs-sidebar-scroll px-1 py-1">
                      <DirectoryTree
                        activePath={currentDoc?.relPath ?? ""}
                        nodes={getNodesForTabKey(tab.key)}
                      />
                    </ScrollShadow>
                  </Tab>
                ))}
              </Tabs>
            ) : (
              <div className="px-2 text-[11px] font-medium text-zinc-500 dark:text-zinc-200">
                Expand
              </div>
            )}
          </div>
        </aside>

        <div className="min-w-0 lg:hidden">
          <div className="px-4 pt-2">
            <Button size="sm" variant="light" onPress={mobileNav.onOpen}>
              目录
            </Button>
          </div>
          <Drawer
            isOpen={mobileNav.isOpen}
            placement="left"
            scrollBehavior="inside"
            onOpenChange={mobileNav.onOpenChange}
          >
            <DrawerContent>
              {(onClose) => (
                <>
                  <DrawerHeader className="text-zinc-950 dark:text-white">
                    Aelin
                  </DrawerHeader>
                  <DrawerBody>
                    <Tabs
                      aria-label="Docs sections"
                      classNames={tabsClassNames}
                      color="default"
                      radius="md"
                      selectedKey={selectedTabKey}
                      size="sm"
                      variant="underlined"
                      onSelectionChange={(key) => setSelectedTabKey(String(key))}
                    >
                      {availableTabs.map((tab) => (
                        <Tab key={tab.key} title={tab.title}>
                          <ScrollShadow className="max-h-[70vh] px-1 py-1">
                            <DirectoryTree
                              activePath={currentDoc?.relPath ?? ""}
                              nodes={getNodesForTabKey(tab.key)}
                              onNavigate={onClose}
                            />
                          </ScrollShadow>
                        </Tab>
                      ))}
                    </Tabs>
                  </DrawerBody>
                </>
              )}
            </DrawerContent>
          </Drawer>
        </div>

        <div className="docs-main min-w-0">
          {currentDoc ? (
            <DocContent currentDoc={currentDoc} docPathSet={docPathSet} />
          ) : (
            <article className="mx-auto max-w-3xl rounded-xl border border-zinc-200/80 bg-white/70 p-6 dark:border-white/10 dark:bg-white/5">
              <h1 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
                Docs Not Found
              </h1>
              <p className="mt-3 text-zinc-700 dark:text-zinc-50">
                未找到可展示的文档，请确认上一级目录存在{" "}
                <code className="rounded bg-zinc-100 px-1 py-0.5 text-[0.9em] text-zinc-950 dark:bg-white/10 dark:text-white">
                  docs/aelin-docs-foundation
                </code>{" "}
                下的 Markdown 文件。
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
