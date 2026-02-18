import type { AppProps } from "next/app";

import clsx from "clsx";
import { HeroUIProvider } from "@heroui/system";
import { ThemeProvider as NextThemesProvider } from "next-themes";
import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";

import { fontSans, fontMono } from "@/config/fonts";
import "@/styles/globals.css";

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const [isRouteTransitioning, setIsRouteTransitioning] = useState(false);
  const [routeAnimState, setRouteAnimState] = useState<"entering" | "leaving">(
    "entering",
  );
  const routeDoneTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (process.env.NODE_ENV === "production") {
      void router.prefetch("/docs");
    }

    void fetch("/api/docs-manifest")
      .then(async (response) => {
        if (!response.ok) return;
        const payload = (await response.json()) as {
          searchEntries?: Array<{ slug?: string[] }>;
        };

        const warmTargets = (payload.searchEntries ?? [])
          .slice(0, 4)
          .map((entry) => {
            const slug = entry.slug ?? [];

            if (!slug.length) return "/docs";

            return `/docs/${slug.map((segment) => encodeURIComponent(segment)).join("/")}`;
          });

        if (process.env.NODE_ENV === "production") {
          await Promise.allSettled(
            warmTargets.map((href) => router.prefetch(href)),
          );
        }
      })
      .catch(() => undefined);
  }, [router]);

  useEffect(() => {
    if (process.env.NODE_ENV !== "development") {
      return;
    }

    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    const warmupDocsPage = () => {
      void fetch("/docs", {
        cache: "no-store",
        credentials: "same-origin",
      }).catch(() => undefined);
    };

    timeoutId = setTimeout(warmupDocsPage, 60);

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, []);

  useEffect(() => {
    const onRouteStart = () => {
      if (routeDoneTimerRef.current) {
        clearTimeout(routeDoneTimerRef.current);
        routeDoneTimerRef.current = null;
      }
      setIsRouteTransitioning(true);
      setRouteAnimState("leaving");
    };
    const onRouteDone = () => {
      setRouteAnimState("entering");
      routeDoneTimerRef.current = setTimeout(() => {
        setIsRouteTransitioning(false);
        routeDoneTimerRef.current = null;
      }, 220);
    };

    router.events.on("routeChangeStart", onRouteStart);
    router.events.on("routeChangeComplete", onRouteDone);
    router.events.on("routeChangeError", onRouteDone);

    return () => {
      if (routeDoneTimerRef.current) {
        clearTimeout(routeDoneTimerRef.current);
        routeDoneTimerRef.current = null;
      }
      router.events.off("routeChangeStart", onRouteStart);
      router.events.off("routeChangeComplete", onRouteDone);
      router.events.off("routeChangeError", onRouteDone);
    };
  }, [router.events]);

  return (
    <HeroUIProvider navigate={router.push}>
      <NextThemesProvider attribute="class" defaultTheme="light">
        <div className="route-motion-root">
          <div
            aria-hidden="true"
            className={clsx(
              "route-curtain",
              isRouteTransitioning && "route-curtain-active",
            )}
          />
          <div
            key={router.asPath.split("#")[0]}
            className="route-page-shell"
            data-route-state={routeAnimState}
          >
            <Component {...pageProps} />
          </div>
        </div>
      </NextThemesProvider>
    </HeroUIProvider>
  );
}

export const fonts = {
  sans: fontSans.style.fontFamily,
  mono: fontMono.style.fontFamily,
};
