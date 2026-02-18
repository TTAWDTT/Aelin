import {
  Navbar as HeroUINavbar,
  NavbarContent,
  NavbarMenu,
  NavbarMenuToggle,
  NavbarBrand,
  NavbarItem,
  NavbarMenuItem,
} from "@heroui/navbar";
import { Link } from "@heroui/link";
import { Avatar } from "@heroui/avatar";
import NextLink from "next/link";
import { useRouter } from "next/router";
import clsx from "clsx";
import { useCallback } from "react";

import { siteConfig } from "@/config/site";
import { ThemeSwitch } from "@/components/theme-switch";
import { GithubIcon } from "@/components/icons";

export const Navbar = () => {
  const router = useRouter();
  const shouldPrefetch = process.env.NODE_ENV === "production";

  const navLinkClassName = useCallback(
    (isActive: boolean) =>
      clsx(
        "inline-flex items-center rounded-md px-2 py-1 text-sm font-medium transition-all duration-150 ease-out will-change-transform",
        "text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950 hover:-translate-y-px hover:shadow-[0_10px_20px_-16px_rgba(0,0,0,0.55)]",
        "dark:text-white/90 dark:hover:bg-white/10 dark:hover:text-white dark:hover:shadow-[0_10px_20px_-16px_rgba(0,0,0,0.85)]",
        isActive &&
          "bg-zinc-100 text-zinc-950 shadow-[0_10px_20px_-16px_rgba(0,0,0,0.55)] dark:bg-white/10 dark:text-white dark:shadow-[0_10px_20px_-16px_rgba(0,0,0,0.85)]",
      ),
    [],
  );

  return (
    <HeroUINavbar
      className="navbar-surface border-b border-zinc-200/70 bg-white/58 backdrop-blur-md dark:border-white/15 dark:bg-black/44"
      maxWidth="xl"
      position="sticky"
    >
      <NavbarContent className="basis-1/5 sm:basis-full" justify="start">
        <NavbarBrand className="gap-3 max-w-fit">
          <Link
            as={NextLink}
            className="flex items-center justify-start gap-1 rounded-md px-1.5 py-1 transition-colors hover:bg-zinc-100/70 dark:hover:bg-white/5"
            href="/"
            prefetch={shouldPrefetch}
          >
            <Avatar
              isBordered
              className="h-7 w-7"
              name="Aelin"
              src="/logo.ico"
            />
            <p className="font-bold text-inherit">Aelin</p>
          </Link>
        </NavbarBrand>
        <div className="hidden lg:flex gap-4 justify-start ml-2">
          {siteConfig.navItems.map((item) => {
            const path = router.asPath.split("?")[0] ?? "/";
            const isActive =
              item.href === "/"
                ? path === "/"
                : path === item.href || path.startsWith(`${item.href}/`);

            return (
              <NavbarItem key={item.href}>
                <Link
                  aria-current={isActive ? "page" : undefined}
                  as={NextLink}
                  className={navLinkClassName(isActive)}
                  href={item.href}
                  prefetch={shouldPrefetch}
                >
                  {item.label}
                </Link>
              </NavbarItem>
            );
          })}
        </div>
      </NavbarContent>

      <NavbarContent
        className="hidden sm:flex basis-1/5 sm:basis-full"
        justify="end"
      >
        <NavbarItem className="hidden sm:flex gap-2">
          <Link isExternal href={siteConfig.links.github} title="GitHub">
            <GithubIcon className="text-zinc-500 transition-colors hover:text-zinc-900 dark:text-white/70 dark:hover:text-white" />
          </Link>
          <ThemeSwitch />
        </NavbarItem>
      </NavbarContent>

      <NavbarContent className="sm:hidden basis-1 pl-4" justify="end">
        <Link isExternal href={siteConfig.links.github}>
          <GithubIcon className="text-zinc-500 dark:text-white/70" />
        </Link>
        <ThemeSwitch />
        <NavbarMenuToggle />
      </NavbarContent>

      <NavbarMenu>
        <div className="mx-4 mt-2 flex flex-col gap-2">
          {siteConfig.navMenuItems.map((item) => (
            <NavbarMenuItem key={item.href}>
              <Link
                as={NextLink}
                href={item.href}
                prefetch={shouldPrefetch}
                size="lg"
              >
                {item.label}
              </Link>
            </NavbarMenuItem>
          ))}
        </div>
      </NavbarMenu>
    </HeroUINavbar>
  );
};
