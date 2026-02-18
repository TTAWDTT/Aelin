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
  const routeShowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const routeSafetyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  useEffect(() => {
    const clearRouteTimers = () => {
      if (routeShowTimerRef.current) {
        clearTimeout(routeShowTimerRef.current);
        routeShowTimerRef.current = null;
      }
      if (routeSafetyTimerRef.current) {
        clearTimeout(routeSafetyTimerRef.current);
        routeSafetyTimerRef.current = null;
      }
    };

    const onRouteStart = () => {
      clearRouteTimers();
      setRouteAnimState("leaving");
      routeShowTimerRef.current = setTimeout(() => {
        setIsRouteTransitioning(true);
        routeShowTimerRef.current = null;
      }, 120);
      routeSafetyTimerRef.current = setTimeout(() => {
        setIsRouteTransitioning(false);
        setRouteAnimState("entering");
        routeSafetyTimerRef.current = null;
      }, 8000);
    };
    const onRouteDone = () => {
      clearRouteTimers();
      setRouteAnimState("entering");
      setIsRouteTransitioning(false);
    };
    const onHashChangeDone = () => {
      clearRouteTimers();
      setIsRouteTransitioning(false);
      setRouteAnimState("entering");
    };

    router.events.on("routeChangeStart", onRouteStart);
    router.events.on("routeChangeComplete", onRouteDone);
    router.events.on("routeChangeError", onRouteDone);
    router.events.on("hashChangeComplete", onHashChangeDone);

    return () => {
      clearRouteTimers();
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
            style={{ display: isRouteTransitioning ? "flex" : "none" }}
          >
            <div className="route-loading-card">
              <Image
                unoptimized
                alt="Aelin loading"
                className="route-loading-gif"
                height={144}
                src="/love.gif"
                width={144}
              />
              <p className="route-loading-text">Aelin is loading...</p>
            </div>
          </div>
          <div
            key={router.asPath.split("#")[0]}
            aria-hidden={isRouteTransitioning}
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
