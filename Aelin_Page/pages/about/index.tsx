import type { GetStaticProps } from "next";

import { Code } from "@heroui/code";
import { Snippet } from "@heroui/snippet";
import { createRoot, type Root } from "react-dom/client";
import { memo, useEffect, useRef } from "react";

import DefaultLayout from "@/layouts/default";
import { getAboutPageData, type AboutPageData } from "@/lib/about";

type AboutPageProps = {
  aboutPage: AboutPageData | null;
};

const AboutContent = memo(function AboutContent({
  aboutPage,
}: {
  aboutPage: AboutPageData;
}) {
  const contentRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const contentElement = contentRef.current;

    if (!contentElement) return;

    const roots: Root[] = [];
    const preBlocks = Array.from(contentElement.querySelectorAll("pre"));

    for (const preBlock of preBlocks) {
      const codeElement = preBlock.querySelector("code");

      if (!codeElement) continue;

      const codeText = (codeElement.textContent ?? "").replace(/\r\n/g, "\n");

      if (!codeText.trim()) continue;

      const normalizedCode = codeText.replace(/\n$/, "");
      const lines = normalizedCode.split("\n");
      const languageToken =
        codeElement.className
          .split(/\s+/)
          .find((token) => token.startsWith("language-")) ?? "";
      const language = languageToken.replace(/^language-/, "");
      const mountNode = document.createElement("div");
      const root = createRoot(mountNode);

      preBlock.replaceWith(mountNode);
      root.render(
        <Snippet
          fullWidth
          className="docs-heroui-snippet my-5"
          classNames={{
            content: "w-full",
            pre: "w-full overflow-x-auto whitespace-pre text-[13px] leading-6",
          }}
          codeString={normalizedCode}
          color="warning"
          hideSymbol={!language}
          radius="md"
          symbol={language ? language.toUpperCase() : undefined}
          variant="flat"
        >
          {lines}
        </Snippet>,
      );
      roots.push(root);
    }

    const inlineCodeElements = Array.from(
      contentElement.querySelectorAll("code"),
    ).filter((codeElement) => !codeElement.closest("pre"));

    for (const inlineCodeElement of inlineCodeElements) {
      const codeText = inlineCodeElement.textContent ?? "";

      if (!codeText.trim()) continue;

      const mountNode = document.createElement("span");
      const root = createRoot(mountNode);

      inlineCodeElement.replaceWith(mountNode);
      root.render(
        <Code color="warning" radius="sm" size="sm">
          {codeText}
        </Code>,
      );
      roots.push(root);
    }

    return () => {
      roots.forEach((root) => root.unmount());
    };
  }, [aboutPage.contentHtml, aboutPage.relPath]);

  return (
    <article className="mx-auto max-w-4xl">
      <header className="border-b border-zinc-200/80 pb-5 dark:border-white/10">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.08em] text-zinc-600 dark:text-white">
          {aboutPage.relPath}
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-white md:text-[2.25rem]">
          {aboutPage.title}
        </h1>
        {aboutPage.description ? (
          <p className="mt-3 max-w-3xl text-base text-zinc-700 dark:text-white/90">
            {aboutPage.description}
          </p>
        ) : null}
        {aboutPage.date ? (
          <p className="mt-3 text-sm text-zinc-600 dark:text-white/80">
            Updated {aboutPage.date}
          </p>
        ) : null}
      </header>
      <div className="pt-6">
        <article
          dangerouslySetInnerHTML={{ __html: aboutPage.contentHtml }}
          ref={contentRef}
          className="docs-markdown about-markdown"
        />
      </div>
    </article>
  );
});

export default function AboutPage({ aboutPage }: AboutPageProps) {
  return (
    <DefaultLayout>
      <section className="docs-shell w-full pb-10 pt-0">
        {aboutPage ? (
          <AboutContent aboutPage={aboutPage} />
        ) : (
          <article className="mx-auto max-w-3xl rounded-xl border border-zinc-200/80 bg-white/70 p-6 dark:border-white/10 dark:bg-white/5">
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
              About Not Found
            </h1>
            <p className="mt-3 text-zinc-700 dark:text-white/90">
              未找到可展示的文档，请确认项目中存在{" "}
              <Code color="warning" radius="sm" size="sm">
                content/about/about.md
              </Code>
              。
            </p>
          </article>
        )}
      </section>
    </DefaultLayout>
  );
}

export const getStaticProps: GetStaticProps<AboutPageProps> = async () => {
  return {
    props: {
      aboutPage: getAboutPageData(),
    },
  };
};
