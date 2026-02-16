import { Lora as FontMono, Lora as FontSans } from "next/font/google";
import localFont from "next/font/local";

export const fontSans = FontSans({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const fontMono = FontMono({
  subsets: ["latin"],
  variable: "--font-mono",
});

// 鹜霞文楷
export const fontChinese = localFont({
  src: [
    {
      path: "../public/fonts/LXGWWenKai-Medium.ttf",
      weight: "400",
      style: "normal",
    },
  ],
  display: "swap",
  variable: "--font-cn-heading",
});
