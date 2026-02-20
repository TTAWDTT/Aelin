import React from "react";
import clsx from "clsx";

type Props = React.SelectHTMLAttributes<HTMLSelectElement>;

export function Select({ className, children, ...rest }: Props) {
  return (
    <select
      className={clsx(
        "focus-ring w-full rounded-lg border border-mist/70 bg-paper/70 px-3 py-2 text-sm",
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  );
}
