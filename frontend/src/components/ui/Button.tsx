import React from "react";
import clsx from "clsx";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "solid" | "ghost" | "subtle";
  tone?: "ink" | "orange" | "blue" | "green";
  size?: "sm" | "md";
};

export function Button({
  className,
  variant = "solid",
  tone = "ink",
  size = "md",
  ...rest
}: Props) {
  const base =
    "focus-ring inline-flex items-center justify-center gap-2 rounded-lg font-heading text-sm transition disabled:opacity-55 disabled:cursor-not-allowed";
  const paddings = size === "sm" ? "px-3 py-1.5" : "px-3.5 py-2";

  const toneClass =
    tone === "orange"
      ? "bg-accent-orange text-paper border-accent-orange/60"
      : tone === "blue"
        ? "bg-accent-blue text-paper border-accent-blue/60"
        : tone === "green"
          ? "bg-accent-green text-paper border-accent-green/60"
          : "bg-ink text-paper border-ink/70";

  const variantClass =
    variant === "ghost"
      ? "bg-transparent text-ink border border-mist/70 hover:border-stone/70"
      : variant === "subtle"
        ? "bg-paper/70 text-ink border border-mist/70 hover:bg-paper"
        : `border ${toneClass} hover:brightness-[1.03]`;

  return (
    <button className={clsx(base, paddings, variantClass, className)} {...rest} />
  );
}
