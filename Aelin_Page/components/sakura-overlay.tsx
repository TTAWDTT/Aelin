import type { CSSProperties } from "react";

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

function buildPetal(index: number): SakuraPetal {
  const left = 2 + unitRand(index, 12.9898) * 96;
  const size = 10 + unitRand(index, 37.719) * 12;
  const duration = 9 + unitRand(index, 78.233) * 10;
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

const PETAL_COUNT = 56;
const PETALS = Array.from({ length: PETAL_COUNT }, (_, index) =>
  buildPetal(index),
);

export function SakuraOverlay() {
  return (
    <div aria-hidden className="sakura-layer">
      {PETALS.map((petal, index) => (
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
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}
