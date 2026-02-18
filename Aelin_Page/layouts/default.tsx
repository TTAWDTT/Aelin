import { Link } from "@heroui/link";
import { useRouter } from "next/router";

import { Head } from "./head";

import { Navbar } from "@/components/navbar";
import { SakuraOverlay } from "@/components/sakura-overlay";

export default function DefaultLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const showSakura = !router.pathname.startsWith("/docs");

  return (
    <div className="app-shell relative flex h-screen flex-col">
      <Head />
      {showSakura ? <SakuraOverlay /> : null}
      <Navbar />
      <main className="container mx-auto max-w-7xl flex-grow px-6 pt-14">
        {children}
      </main>
      <footer className="w-full flex items-center justify-center py-3">
        <Link
          isExternal
          className="flex items-center gap-1 text-current"
          href="https://www.heroui.com"
          title="heroui.com homepage"
        >
          <span className="text-zinc-600 dark:text-zinc-200">Powered by</span>
          <p className="text-zinc-900 dark:text-white">HeroUI</p>
        </Link>
      </footer>
    </div>
  );
}
