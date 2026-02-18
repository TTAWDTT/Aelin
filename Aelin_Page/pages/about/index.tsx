import type { GetStaticProps } from "next";

import { Code } from "@heroui/code";
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
    <DefaultLayout
      description={aboutPage?.description}
      title={aboutPage?.title ?? "About"}
    >
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
