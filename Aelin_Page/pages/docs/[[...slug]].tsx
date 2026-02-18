import type { GetStaticPaths, GetStaticProps } from "next";

import dynamic from "next/dynamic";
import { useRouter } from "next/router";
import clsx from "clsx";
import NextLink from "next/link";
import {
  memo,
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Accordion, AccordionItem } from "@heroui/accordion";
import { Button } from "@heroui/button";
import { Code } from "@heroui/code";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
} from "@heroui/drawer";
import { Link } from "@heroui/link";
import { ScrollShadow } from "@heroui/scroll-shadow";
import { useDisclosure } from "@heroui/use-disclosure";

import DefaultLayout from "@/layouts/default";
import {
  findDocBySlug,
  getAllDocs,
  getAllDocSlugs,
  getDocsSearchEntries,
  getDocsTree,
  type DocHeading,
  type DocRecord,
  type DocSearchEntry,
  type DocTreeNode,
} from "@/lib/docs";

type DocsPageProps = {
  currentDoc: DocRecord | null;
  initialSearchEntries: DocSearchEntry[];
  initialTree: DocTreeNode[];
};

const DocsClientEffects = dynamic(
  () =>
    import("@/components/docs/docs-client-effects").then(
      (module) => module.DocsClientEffects,
    ),
  { ssr: false },
);

const SIDEBAR_WIDTH_EXPANDED_PX = 280;
const SIDEBAR_WIDTH_COLLAPSED_PX = 56;
const TOP_OFFSET_PX = 56;
const HIDDEN_OVERVIEW_DOCS = new Set(["README.md", "NAVIGATION.md"]);
const SIDEBAR_STATE_KEY = "aelin-docs-sidebar-collapsed";

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
  if (!slug.length) return "/docs";

  return `/docs/${encodePath(slug.join("/"))}`;
}

function isDocsRoute(url: unknown): url is string {
  return typeof url === "string" && url.startsWith("/docs");
}

const SHOULD_PREFETCH = process.env.NODE_ENV === "production";

const DirectoryTree = memo(function DirectoryTree({
  nodes,
  activePath,
  onNavigate,
}: {
  nodes: DocTreeNode[];
  activePath: string;
  onNavigate?: (targetRelPath?: string) => void;
}) {
  const folders = nodes.filter((node) => node.type === "folder");
  const files = nodes.filter((node) => node.type === "file");

  return (
    <div className="space-y-2">
      {folders.map((folder) => (
        <div key={folder.key}>
          <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-600 dark:text-white">
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
        const handleNavigate = () => onNavigate?.(node.relPath);

        return (
          <Link
            key={node.key}
            as={NextLink}
            className={clsx(
              "block rounded-md px-3 py-1.5 text-sm transition-colors",
              isActive
                ? "bg-zinc-100 font-semibold text-zinc-950 dark:bg-white/10 dark:text-white"
                : "text-zinc-700 hover:bg-zinc-100/70 dark:text-white/90 dark:hover:bg-white/5",
            )}
            href={toDocHref(node.slug)}
            prefetch={SHOULD_PREFETCH}
            onClick={handleNavigate}
            onPress={handleNavigate}
          >
            {node.title}
          </Link>
        );
      })}
    </div>
  );
});

const SearchResultList = memo(function SearchResultList({
  items,
  status,
  onNavigate,
}: {
  items: DocSearchEntry[];
  status: "idle" | "loading" | "ready" | "error";
  onNavigate?: (targetRelPath?: string) => void;
}) {
  if (status === "loading") {
    return (
      <p className="px-2 py-3 text-sm text-zinc-500 dark:text-white/70">
        Loading search index...
      </p>
    );
  }

  if (status === "error") {
    return (
      <p className="px-2 py-3 text-sm text-zinc-500 dark:text-white/70">
        Search is temporarily unavailable.
      </p>
    );
  }

  if (!items.length) {
    return (
      <p className="px-2 py-3 text-sm text-zinc-500 dark:text-white/70">
        No results.
      </p>
    );
  }

  return (
    <div className="space-y-1 px-1">
      {items.slice(0, 20).map((item) => {
        const handleNavigate = () => onNavigate?.(item.relPath);

        return (
          <Link
            key={item.relPath}
            as={NextLink}
            className="block rounded-md px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-100/70 dark:text-white/90 dark:hover:bg-white/5"
            href={toDocHref(item.slug)}
            prefetch={SHOULD_PREFETCH}
            onClick={handleNavigate}
            onPress={handleNavigate}
          >
            <p className="font-medium text-zinc-900 dark:text-white">
              {item.title}
            </p>
            {item.description ? (
              <p className="line-clamp-2 text-xs text-zinc-500 dark:text-white/70">
                {item.description}
              </p>
            ) : null}
          </Link>
        );
      })}
    </div>
  );
});

const Toc = memo(function Toc({
  headings,
  activeHeadingId,
}: {
  headings: DocHeading[];
  activeHeadingId: string;
}) {
  if (!headings.length) return null;

  return (
    <aside className="docs-toc hidden xl:block">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-600 dark:text-white/80">
        On this page
      </p>
      <nav className="space-y-1">
        {headings.map((heading) => (
          <a
            key={heading.id}
            className={clsx(
              "block rounded px-2 py-1 text-sm transition-colors",
              heading.level === 3 ? "ml-3" : "ml-0",
              activeHeadingId === heading.id
                ? "bg-zinc-100 text-zinc-950 dark:bg-white/10 dark:text-white"
                : "text-zinc-600 hover:bg-zinc-100/70 dark:text-white/70 dark:hover:bg-white/5",
            )}
            href={`#${heading.id}`}
          >
            {heading.text}
          </a>
        ))}
      </nav>
    </aside>
  );
});

const DocContent = memo(function DocContent({
  currentDoc,
}: {
  currentDoc: DocRecord;
}) {
  const contentRef = useRef<HTMLElement | null>(null);

  // Lightweight event-delegation for copy buttons (no React roots needed)
  useEffect(() => {
    const el = contentRef.current;

    if (!el) return;

    const handler = (e: MouseEvent) => {
      const btn = (e.target as HTMLElement).closest(".docs-code-copy");

      if (!btn || !(btn instanceof HTMLButtonElement)) return;

      const block = btn.closest(".docs-code-block");
      const code = block?.querySelector("pre code");

      if (!code) return;

      navigator.clipboard
        .writeText(code.textContent ?? "")
        .then(() => {
          btn.textContent = "Copied!";
          setTimeout(() => {
            btn.textContent = "Copy";
          }, 2000);
        })
        .catch(() => {
          /* clipboard write failed — ignore */
        });
    };

    el.addEventListener("click", handler);

    return () => el.removeEventListener("click", handler);
  }, [currentDoc.contentHtml, currentDoc.relPath]);

  return (
    <article className="mx-auto max-w-4xl">
      <header className="border-b border-zinc-200/80 pb-5 dark:border-white/10">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.08em] text-zinc-600 dark:text-white">
          {currentDoc.relPath}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white md:text-[2.25rem]">
          {currentDoc.title}
        </h1>
        {currentDoc.description ? (
          <p className="mt-3 max-w-3xl text-base text-zinc-700 dark:text-white/90">
            {currentDoc.description}
          </p>
        ) : null}
        {currentDoc.date ? (
          <p className="mt-3 text-sm text-zinc-600 dark:text-white/80">
            Updated {currentDoc.date}
          </p>
        ) : null}
      </header>
      <div className="pt-6">
        <article
          dangerouslySetInnerHTML={{ __html: currentDoc.contentHtml }}
          ref={contentRef}
          className="docs-markdown"
        />
      </div>
    </article>
  );
});

function DocsNav({
  tree,
  manifestStatus,
  rootFiles,
  topLevelFolders,
  activePath,
  defaultExpandedKeys,
  onNavigate,
  searchQuery,
  searchResults,
  searchStatus,
  onSearch,
}: {
  tree: DocTreeNode[];
  manifestStatus: "idle" | "loading" | "ready" | "error";
  rootFiles: Extract<DocTreeNode, { type: "file" }>[];
  topLevelFolders: Extract<DocTreeNode, { type: "folder" }>[];
  activePath: string;
  defaultExpandedKeys: string[];
  onNavigate?: (targetRelPath?: string) => void;
  searchQuery: string;
  searchResults: DocSearchEntry[];
  searchStatus: "idle" | "loading" | "ready" | "error";
  onSearch: (value: string) => void;
}) {
  return (
    <ScrollShadow className="docs-sidebar-scroll px-1 py-1">
      <div className="px-1 pb-3">
        <input
          className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-zinc-400 dark:border-white/15 dark:bg-white/5 dark:text-white"
          placeholder="Search docs..."
          value={searchQuery}
          onChange={(event) => onSearch(event.target.value)}
        />
      </div>

      {searchQuery.trim() ? (
        <SearchResultList
          items={searchResults}
          status={searchStatus === "ready" ? "ready" : searchStatus}
          onNavigate={onNavigate}
        />
      ) : (
        <>
          {rootFiles.length ? (
            <div className="pb-3">
              <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-600 dark:text-white">
                Overview
              </p>
              <div className="pl-1">
                <DirectoryTree
                  activePath={activePath}
                  nodes={rootFiles}
                  onNavigate={onNavigate}
                />
              </div>
            </div>
          ) : null}

          <Accordion
            defaultExpandedKeys={defaultExpandedKeys}
            itemClasses={{
              content: "px-0 pb-2 pt-1",
              indicator: "text-zinc-500 dark:text-white/70",
              title:
                "text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-700 dark:text-white",
              trigger:
                "px-2 py-2 rounded-md hover:bg-zinc-100/70 dark:hover:bg-white/5",
            }}
            selectionBehavior="toggle"
            selectionMode="multiple"
            showDivider={false}
            variant="light"
          >
            {topLevelFolders.map((folder) => (
              <AccordionItem
                key={folder.name}
                aria-label={folder.name}
                title={titleCase(formatLabel(folder.name))}
              >
                <div className="pl-1">
                  <DirectoryTree
                    activePath={activePath}
                    nodes={folder.children}
                    onNavigate={onNavigate}
                  />
                </div>
              </AccordionItem>
            ))}
          </Accordion>

          {!rootFiles.length && !topLevelFolders.length ? (
            <div className="px-2 text-sm text-zinc-600 dark:text-white/80">
              {manifestStatus === "loading" || manifestStatus === "idle" ? (
                "Loading docs..."
              ) : tree.length ? (
                <DirectoryTree
                  activePath={activePath}
                  nodes={tree}
                  onNavigate={onNavigate}
                />
              ) : (
                "No docs found."
              )}
            </div>
          ) : null}
        </>
      )}
    </ScrollShadow>
  );
}

export default function DocsPage({
  currentDoc,
  initialSearchEntries,
  initialTree,
}: DocsPageProps) {
  const router = useRouter();
  const [tree, setTree] = useState<DocTreeNode[]>(initialTree);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchEntries, setSearchEntries] =
    useState<DocSearchEntry[]>(initialSearchEntries);
  const [manifestStatus, setManifestStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >(initialTree.length || initialSearchEntries.length ? "ready" : "idle");
  const [isRouteLoading, setIsRouteLoading] = useState(false);
  const [optimisticActivePath, setOptimisticActivePath] = useState("");
  const [activeHeadingId, setActiveHeadingId] = useState("");
  const mobileNav = useDisclosure();
  const currentPath = currentDoc?.relPath ?? "";
  const activePath = optimisticActivePath || currentPath;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(SIDEBAR_STATE_KEY);

    if (saved === "1") setIsSidebarCollapsed(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      SIDEBAR_STATE_KEY,
      isSidebarCollapsed ? "1" : "0",
    );
  }, [isSidebarCollapsed]);

  useEffect(() => {
    const onRouteStart = (url: string) => {
      if (isDocsRoute(url)) {
        setIsRouteLoading(true);
      }
    };

    const onRouteDone = (url: string) => {
      if (isDocsRoute(url)) {
        setIsRouteLoading(false);
        setOptimisticActivePath("");
      }
    };

    const onRouteError = (_error: unknown, url: string) => {
      if (isDocsRoute(url)) {
        setIsRouteLoading(false);
        setOptimisticActivePath("");
      }
    };

    router.events.on("routeChangeStart", onRouteStart);
    router.events.on("routeChangeComplete", onRouteDone);
    router.events.on("routeChangeError", onRouteError);

    return () => {
      router.events.off("routeChangeStart", onRouteStart);
      router.events.off("routeChangeComplete", onRouteDone);
      router.events.off("routeChangeError", onRouteError);
    };
  }, [router.events]);

  useEffect(() => {
    setOptimisticActivePath("");
    setIsRouteLoading(false);
  }, [currentPath]);

  const sidebarWidth = isSidebarCollapsed
    ? SIDEBAR_WIDTH_COLLAPSED_PX
    : SIDEBAR_WIDTH_EXPANDED_PX;

  const onToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed((prev) => !prev);
  }, []);

  const loadManifest = useCallback(async () => {
    if (manifestStatus === "ready" || manifestStatus === "loading") {
      return;
    }

    setManifestStatus("loading");

    try {
      const response = await fetch("/api/docs-manifest");

      if (!response.ok) {
        throw new Error("failed to load docs manifest");
      }

      const payload = (await response.json()) as {
        tree?: DocTreeNode[];
        entries?: DocSearchEntry[];
        searchEntries?: DocSearchEntry[];
      };

      setTree(payload.tree ?? []);
      setSearchEntries(payload.searchEntries ?? payload.entries ?? []);
      setManifestStatus("ready");
    } catch {
      setManifestStatus("error");
    }
  }, [manifestStatus]);

  useEffect(() => {
    if (manifestStatus === "idle") {
      void loadManifest();
    }
  }, [loadManifest, manifestStatus]);

  const onSearch = useCallback(
    (value: string) => {
      setSearchQuery(value);

      if (value.trim() && manifestStatus === "idle") {
        void loadManifest();
      }
    },
    [loadManifest, manifestStatus],
  );

  const onActiveHeadingChange = useCallback((headingId: string) => {
    setActiveHeadingId(headingId);
  }, []);

  const onNavigate = useCallback(
    (targetRelPath?: string) => {
      if (!targetRelPath || targetRelPath === currentPath) {
        return;
      }

      setOptimisticActivePath(targetRelPath);
      setIsRouteLoading(true);
    },
    [currentPath],
  );

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
      (
        tree.filter((node) => node.type === "file") as Extract<
          DocTreeNode,
          { type: "file" }
        >[]
      ).filter((node) => !HIDDEN_OVERVIEW_DOCS.has(node.relPath)),
    [tree],
  );

  const searchResults = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    if (!query) return [];

    return searchEntries
      .map((entry) => {
        const haystack =
          `${entry.title} ${entry.description} ${entry.relPath}`.toLowerCase();
        const exactTitle = entry.title.toLowerCase().includes(query) ? 3 : 0;
        const exactPath = entry.relPath.toLowerCase().includes(query) ? 2 : 0;
        const weak = haystack.includes(query) ? 1 : 0;

        return { entry, score: exactTitle + exactPath + weak };
      })
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((item) => item.entry);
  }, [searchEntries, searchQuery]);

  const defaultExpandedKeys = useMemo(() => {
    const relPath = currentDoc?.relPath ?? "";
    const firstSegment = relPath.split("/")[0] ?? "";
    const hasSection = topLevelFolders.some(
      (folder) => folder.name === firstSegment,
    );

    return hasSection ? [firstSegment] : [];
  }, [currentDoc?.relPath, topLevelFolders]);

  return (
    <DefaultLayout
      description={currentDoc?.description}
      title={currentDoc?.title ?? "Docs"}
    >
      {currentDoc ? (
        <DocsClientEffects
          headings={currentDoc.headings ?? []}
          onActiveHeadingChange={onActiveHeadingChange}
        />
      ) : null}
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
              isIconOnly
              aria-label={
                isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"
              }
              className="min-w-0"
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
              <DocsNav
                activePath={activePath}
                defaultExpandedKeys={defaultExpandedKeys}
                manifestStatus={manifestStatus}
                rootFiles={rootFiles}
                searchQuery={searchQuery}
                searchResults={searchResults}
                searchStatus={manifestStatus}
                topLevelFolders={topLevelFolders}
                tree={tree}
                onNavigate={onNavigate}
                onSearch={onSearch}
              />
            ) : (
              <div className="px-2 text-[11px] font-medium text-zinc-500 dark:text-white/80">
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
                    <DocsNav
                      activePath={activePath}
                      defaultExpandedKeys={defaultExpandedKeys}
                      manifestStatus={manifestStatus}
                      rootFiles={rootFiles}
                      searchQuery={searchQuery}
                      searchResults={searchResults}
                      searchStatus={manifestStatus}
                      topLevelFolders={topLevelFolders}
                      tree={tree}
                      onNavigate={(targetRelPath) => {
                        onClose();
                        onNavigate(targetRelPath);
                      }}
                      onSearch={onSearch}
                    />
                  </DrawerBody>
                </>
              )}
            </DrawerContent>
          </Drawer>
        </div>

        <div className="docs-main min-w-0">
          <div className="docs-content-wrap">
            <div
              className={clsx(
                "transition-opacity duration-150",
                isRouteLoading && "pointer-events-none",
              )}
            >
              {currentDoc ? (
                <>
                  <DocContent currentDoc={currentDoc} />
                  <Toc
                    activeHeadingId={activeHeadingId}
                    headings={currentDoc.headings ?? []}
                  />
                </>
              ) : (
                <article className="mx-auto max-w-3xl rounded-xl border border-zinc-200/80 bg-white/70 p-6 dark:border-white/10 dark:bg-white/5">
                  <h1 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
                    Docs Not Found
                  </h1>
                  <p className="mt-3 text-zinc-700 dark:text-white/90">
                    未找到可展示的文档，请确认项目中存在{" "}
                    <Code color="warning" radius="sm" size="sm">
                      content/docs/aelin-docs-foundation
                    </Code>{" "}
                    下的 Markdown 文件。
                  </p>
                </article>
              )}
            </div>
          </div>
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
    fallback: "blocking",
  };
};

export const getStaticProps: GetStaticProps<DocsPageProps> = async ({
  params,
}) => {
  const docs = getAllDocs();
  const initialTree = getDocsTree();
  const initialSearchEntries = getDocsSearchEntries();
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
      currentDoc,
      initialSearchEntries,
      initialTree,
    },
  };
};
