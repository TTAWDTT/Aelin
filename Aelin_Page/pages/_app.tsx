import type { AppProps } from "next/app";

import { HeroUIProvider } from "@heroui/system";
import Image from "next/image";
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
    const onHashChangeDone = () => {
      setIsRouteTransitioning(false);
    };

    router.events.on("routeChangeStart", onRouteStart);
    router.events.on("routeChangeComplete", onRouteDone);
    router.events.on("routeChangeError", onRouteDone);
    router.events.on("hashChangeComplete", onHashChangeDone);

    return () => {
      if (routeDoneTimerRef.current) {
        clearTimeout(routeDoneTimerRef.current);
        routeDoneTimerRef.current = null;
      }
      router.events.off("routeChangeStart", onRouteStart);
      router.events.off("routeChangeComplete", onRouteDone);
      router.events.off("routeChangeError", onRouteDone);
      router.events.off("hashChangeComplete", onHashChangeDone);
    };
  }, [router.events]);

  return (
    <HeroUIProvider navigate={router.push}>
      <NextThemesProvider attribute="class" defaultTheme="light">
        <div className="route-motion-root">
          <div
            aria-hidden={!isRouteTransitioning}
            className={
              isRouteTransitioning
                ? "route-loading-screen route-loading-screen-active"
                : "route-loading-screen"
            }
          >
            <div className="route-loading-card">
              <Image
                unoptimized
                alt="Aelin loading"
                className="route-loading-gif"
                height={132}
                src="/love.gif"
                width={132}
              />
              <p className="route-loading-text">Aelin is loading...</p>
              <span aria-hidden className="route-loading-dots" />
            </div>
          </div>
          <div
            key={router.asPath.split("#")[0]}
            aria-hidden={isRouteTransitioning}
            className={
              isRouteTransitioning
                ? "route-page-shell route-page-shell-dimmed"
                : "route-page-shell"
            }
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
