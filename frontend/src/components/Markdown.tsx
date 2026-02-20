import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize]}
      components={{
        a: (props) => (
          <a
            {...props}
            className="underline decoration-stone/60 hover:decoration-stone focus-ring rounded-sm"
            target="_blank"
            rel="noreferrer"
          />
        ),
        code: (props) => (
          <code {...props} className="rounded bg-mist/70 px-1 py-0.5 text-[0.92em]" />
        ),
        pre: (props) => (
          <pre
            {...props}
            className="rounded-xl border border-mist/70 bg-paper/60 p-3 overflow-auto"
          />
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

