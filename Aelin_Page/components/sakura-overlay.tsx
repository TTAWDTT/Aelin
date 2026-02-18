import { useRouter } from "next/router";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

type SakuraPetal = {
  delay: string;
  drift: string;
  duration: string;
  left: string;
  opacity: string;
  rotation: string;
  scale: string;
  size: string;
};

function unitRand(index: number, seed: number): number {
  const raw = Math.sin((index + 1) * seed) * 10000;

  return raw - Math.floor(raw);
}

function buildPetal(index: number, speedFactor = 1): SakuraPetal {
  const left = 2 + unitRand(index, 12.9898) * 96;
  const size = 10 + unitRand(index, 37.719) * 12;
  const duration = (9 + unitRand(index, 78.233) * 10) * speedFactor;
  const delay = -1 * unitRand(index, 19.241) * duration;
  const drift = 40 + unitRand(index, 51.911) * 140;
  const opacity = 0.32 + unitRand(index, 91.337) * 0.38;
  const rotation = unitRand(index, 29.873) * 360;
  const scale = 0.8 + unitRand(index, 63.019) * 0.45;

  return {
    delay: `${delay.toFixed(2)}s`,
    drift: `${drift.toFixed(0)}px`,
    duration: `${duration.toFixed(2)}s`,
    left: `${left.toFixed(2)}%`,
    opacity: opacity.toFixed(2),
    rotation: `${rotation.toFixed(0)}deg`,
    scale: scale.toFixed(2),
    size: `${size.toFixed(0)}px`,
  };
}

function pickPetalCount(viewportWidth: number, isDocsPage: boolean): number {
  if (isDocsPage) {
    if (viewportWidth < 640) return 8;
    if (viewportWidth < 1024) return 14;

    return 24;
  }

  if (viewportWidth < 640) return 16;
  if (viewportWidth < 1024) return 28;

  return 48;
}

function applyDeviceTier(baseCount: number): number {
  if (typeof navigator === "undefined") return baseCount;

  const conn = (
    navigator as Navigator & {
      connection?: { saveData?: boolean };
    }
  ).connection;
  const saveData = !!conn?.saveData;
  const cpu = navigator.hardwareConcurrency || 4;

  if (saveData || cpu <= 4) return Math.max(8, Math.floor(baseCount * 0.5));
  if (cpu <= 8) return Math.max(10, Math.floor(baseCount * 0.75));

  return baseCount;
}

export function SakuraOverlay() {
  const router = useRouter();
  const isDocsPage = router.pathname.startsWith("/docs");

  const [petalCount, setPetalCount] = useState(48);
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const updateCount = () => {
      const base = pickPetalCount(window.innerWidth, isDocsPage);

      setPetalCount(applyDeviceTier(base));
    };

    updateCount();
    window.addEventListener("resize", updateCount);

    return () => window.removeEventListener("resize", updateCount);
  }, [isDocsPage]);

  useEffect(() => {
    if (typeof document === "undefined") return;

    const onVisibility = () =>
      setIsVisible(document.visibilityState === "visible");

    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);

    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const petals = useMemo(() => {
    const speedFactor = isDocsPage ? 1.3 : 1;

    return Array.from({ length: petalCount }, (_, index) =>
      buildPetal(index, speedFactor),
    );
  }, [isDocsPage, petalCount]);

  return (
    <div aria-hidden className="sakura-layer">
      {petals.map((petal, index) => (
        <span
          key={`${petal.left}-${petal.duration}-${index}`}
          className="sakura-petal"
          style={
            {
              "--sakura-delay": petal.delay,
              "--sakura-drift": petal.drift,
              "--sakura-duration": petal.duration,
              "--sakura-left": petal.left,
              "--sakura-opacity": petal.opacity,
              "--sakura-rotation": petal.rotation,
              "--sakura-scale": petal.scale,
              "--sakura-size": petal.size,
              animationPlayState: isVisible ? "running" : "paused",
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}
