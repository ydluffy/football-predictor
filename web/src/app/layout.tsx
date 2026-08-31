import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 球赛预测系统",
  description: "对话 + 赛程 + 泊松基线预测（P0）",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-950">
        <header className="border-b border-zinc-200 bg-white">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-900 text-white text-sm font-semibold">
                AI
              </div>
              <div className="leading-tight">
                <div className="text-sm font-semibold">AI 球赛预测系统</div>
                <div className="text-xs text-zinc-500">P0：对话 / 赛程 / 预测</div>
              </div>
            </div>
            <nav className="flex items-center gap-2 text-sm">
              <a className="rounded-md px-3 py-1.5 hover:bg-zinc-100" href="/chat">
                对话
              </a>
              <a className="rounded-md px-3 py-1.5 hover:bg-zinc-100" href="/fixtures">
                赛程
              </a>
              <a className="rounded-md px-3 py-1.5 hover:bg-zinc-100" href="/predictions">
                预测
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
