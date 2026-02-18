import { Html, Head, Main, NextScript } from "next/document";
import clsx from "clsx";

import { fontChinese, fontSans } from "@/config/fonts";

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        {process.env.NODE_ENV === "development" ? (
          <script
            dangerouslySetInnerHTML={{
              __html: `
                (function () {
                  try {
                    if (window.location.pathname.startsWith("/docs")) return;
                    fetch("/docs", { cache: "no-store", credentials: "same-origin" }).catch(function () {});
                    fetch("/api/docs-manifest", { cache: "force-cache", credentials: "same-origin" }).catch(function () {});
                  } catch (e) {}
                })();
              `,
            }}
          />
        ) : null}
      </Head>
      <body
        className={clsx(
          "min-h-screen bg-background font-sans antialiased",
          fontSans.variable,
          fontChinese.variable,
        )}
      >
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
