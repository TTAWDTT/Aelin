import React from "react";
import clsx from "clsx";

type Props = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...rest }: Props) {
  return (
    <input
      className={clsx(
        "focus-ring w-full rounded-lg border border-mist/70 bg-paper/70 px-3 py-2 text-sm",
        "placeholder:text-stone/80",
        className,
      )}
      {...rest}
    />
  );
}
