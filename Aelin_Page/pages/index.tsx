import { type GetStaticProps } from "next";
import { Link } from "@heroui/link";
import { button as buttonStyles } from "@heroui/theme";
import Image from "next/image";
import NextLink from "next/link";
import { useRouter } from "next/router";
import { useEffect } from "react";

import { siteConfig } from "@/config/site";
import { GithubIcon } from "@/components/icons";
import { subtitle, title } from "@/components/primitives";
import { fontChinese } from "@/config/fonts";
import DefaultLayout from "@/layouts/default";
import { getAllDocSlugs } from "@/lib/docs";

type IndexPageProps = {
  docPrefetchHrefs: string[];
};

function toDocHref(slug: string[]): string {
  if (!slug.length) {
    return "/docs";
  }

  return `/docs/${slug.map((segment) => encodeURIComponent(segment)).join("/")}`;
}

export default function IndexPage({ docPrefetchHrefs }: IndexPageProps) {
  const router = useRouter();
  const shouldPrefetch = process.env.NODE_ENV === "production";

  useEffect(() => {
    if (shouldPrefetch) {
      void router.prefetch("/docs");
    }
    void fetch("/api/docs-manifest").catch(() => undefined);

    let cancelled = false;
    let idleId: number | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    if (process.env.NODE_ENV !== "production") {
      return;
    }

    const additionalHrefs = docPrefetchHrefs.filter((href) => href !== "/docs");

    const prefetchAllDocs = async () => {
      for (const href of additionalHrefs) {
        if (cancelled) {
          break;
        }

        try {
          await router.prefetch(href);
        } catch {
          // Ignore transient prefetch failures.
        }
      }
    };

    const runPrefetch = () => {
      void prefetchAllDocs();
    };

    if (typeof window !== "undefined" && "requestIdleCallback" in window) {
      idleId = window.requestIdleCallback(runPrefetch, { timeout: 2000 });
    } else {
      timeoutId = setTimeout(runPrefetch, 800);
    }

    return () => {
      cancelled = true;

      if (typeof window !== "undefined" && idleId !== undefined) {
        window.cancelIdleCallback(idleId);
      }

      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [docPrefetchHrefs, router, shouldPrefetch]);

  return (
    <DefaultLayout>
      <section className="flex flex-col items-center justify-center gap-4 py-8">
        <div className="relative mb-2 h-52 w-52 overflow-hidden rounded-full border-2 border-zinc-200/80 shadow-lg shadow-zinc-300/30 dark:border-white/20 dark:shadow-black/40">
          <Image
            fill
            priority
            alt="Aelin"
            className="object-cover"
            sizes="208px"
            src="/smile.png"
          />
        </div>
        <h1 className={title()}>Aelin</h1>
        <h2
          className={`${subtitle()} ${fontChinese.className} text-center mx-auto`}
        >
          你的个人信息助手
        </h2>
        <div className="flex gap-3">
          <Link
            as={NextLink}
            className={buttonStyles({
              color: "primary",
              radius: "full",
              variant: "shadow",
            })}
            href={siteConfig.links.docs}
            prefetch={shouldPrefetch}
          >
            Documentation
          </Link>
          <Link
            isExternal
            className={buttonStyles({ radius: "full", variant: "bordered" })}
            href={siteConfig.links.github}
          >
            <GithubIcon size={20} />
            GitHub
          </Link>
        </div>
      </section>
    </DefaultLayout>
  );
}

export const getStaticProps: GetStaticProps<IndexPageProps> = async () => {
  const slugs = getAllDocSlugs();
  const docPrefetchHrefs = ["/docs"].concat(
    slugs.map((slug) => toDocHref(slug)),
  );

  return {
    props: {
      docPrefetchHrefs,
    },
  };
};
