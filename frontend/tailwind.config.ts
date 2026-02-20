import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--c-ink) / <alpha-value>)",
        paper: "rgb(var(--c-paper) / <alpha-value>)",
        mist: "rgb(var(--c-mist) / <alpha-value>)",
        stone: "rgb(var(--c-stone) / <alpha-value>)",
        accent: {
          orange: "rgb(var(--c-accent-orange) / <alpha-value>)",
          blue: "rgb(var(--c-accent-blue) / <alpha-value>)",
          green: "rgb(var(--c-accent-green) / <alpha-value>)"
        }
      },
      boxShadow: {
        paper: "0 1px 0 rgba(0,0,0,0.06), 0 12px 40px rgba(0,0,0,0.10)",
      },
      fontFamily: {
        heading: [
          "Poppins",
          "Arial",
          "PingFang SC",
          "Microsoft YaHei",
          "sans-serif",
        ],
        body: [
          "Lora",
          "Georgia",
          "Noto Serif SC",
          "Source Han Serif SC",
          "STSong",
          "serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;

