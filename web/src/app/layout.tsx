import type { Metadata } from "next";
import Link from "next/link";
import { AppNav } from "@/components/AppNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "球赛预测工作台",
  description: "体彩销售日驱动的赛程、预测、赔率与复盘工作台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full" suppressHydrationWarning>
      <body className="flex min-h-full flex-col bg-zinc-50 text-zinc-900 antialiased">
        <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4">
            <Link href="/" className="flex shrink-0 items-center gap-2 py-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-900 text-[11px] font-semibold text-white">
                FP
              </span>
              <span className="text-sm font-semibold text-zinc-900">球赛预测工作台</span>
            </Link>
            <AppNav />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5">{children}</main>
      </body>
    </html>
  );
}
