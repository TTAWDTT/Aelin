import React from "react";
import NextHead from "next/head";

import { siteConfig } from "@/config/site";

type HeadProps = {
  title?: string;
  description?: string;
};

export const Head = ({ title, description }: HeadProps) => {
  const pageTitle = title
    ? `${title} | ${siteConfig.name}`
    : siteConfig.name;
  const pageDescription = description || siteConfig.description;

  return (
    <NextHead>
      <title>{pageTitle}</title>
      <meta key="title" content={pageTitle} property="og:title" />
      <meta content={pageDescription} property="og:description" />
      <meta content={pageDescription} name="description" />
      <meta content="summary" name="twitter:card" />
      <meta content={pageTitle} name="twitter:title" />
      <meta content={pageDescription} name="twitter:description" />
      <meta
        key="viewport"
        content="viewport-fit=cover, width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=0"
        name="viewport"
      />
      <link href="/logo.ico" rel="icon" />
    </NextHead>
  );
};
