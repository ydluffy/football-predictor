import type { Metadata } from "next";
import { AppNav } from "@/components/AppNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "球赛预测工作台",
  description: "比赛数据、预测结果、系统状态与智能助手的一体化工作台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-950">
        <header className="sticky top-0 z-20 border-b border-zinc-200/80 bg-white/90 backdrop-blur">
          <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-zinc-900 text-sm font-semibold text-white shadow-sm">
                FP
              </div>
              <div className="leading-tight">
                <div className="text-sm font-semibold">球赛预测工作台</div>
                <div className="text-xs text-zinc-500">数据接入、比赛预测、系统巡检与智能协作</div>
              </div>
            </div>
            <AppNav />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
