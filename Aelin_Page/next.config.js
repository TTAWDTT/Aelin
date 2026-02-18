/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 60 * 60 * 24 * 7,
  },
  webpack: (config, { dev }) => {
    if (dev) {
      const existingIgnored =
        typeof config.watchOptions?.ignored === "string"
          ? [config.watchOptions.ignored]
          : Array.isArray(config.watchOptions?.ignored)
            ? config.watchOptions.ignored.filter(
                (item) => typeof item === "string" && item.length > 0,
              )
            : [];

      config.watchOptions = {
        ...(config.watchOptions ?? {}),
        ignored: [
          ...existingIgnored,
          "**/content/about/.obsidian/**",
          "**/content/docs/aelin-docs-foundation/.obsidian/**",
        ],
      };
    }

    return config;
  },
};

module.exports = nextConfig;
