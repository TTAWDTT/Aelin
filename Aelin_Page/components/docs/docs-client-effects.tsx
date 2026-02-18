import type { DocHeading } from "@/lib/docs";

import { useEffect } from "react";

type DocsClientEffectsProps = {
  headings: DocHeading[];
  onActiveHeadingChange: (headingId: string) => void;
};

export function DocsClientEffects({
  headings,
  onActiveHeadingChange,
}: DocsClientEffectsProps) {
  useEffect(() => {
    if (!headings.length) {
      onActiveHeadingChange("");

      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

        if (visible[0]?.target?.id) {
          onActiveHeadingChange(visible[0].target.id);
        }
      },
      {
        rootMargin: "-20% 0px -65% 0px",
        threshold: [0.1, 0.4, 0.8],
      },
    );

    headings.forEach((heading) => {
      const element = document.getElementById(heading.id);

      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
  }, [headings, onActiveHeadingChange]);

  return null;
}
