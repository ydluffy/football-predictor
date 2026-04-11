"use client";

import { useMemo, useState } from "react";
import type { ChatMessage } from "@/lib/api";
import { ingestFootballData, postChat } from "@/lib/api";

function todayStr(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "你好，我是你的 AI 球赛预测助手。你可以问我：\n\n- 今天有什么比赛？\n- 给我今天五大联赛的胜平负概率\n\n如果还没入库，我也可以帮你触发导入（需要配置 football-data.org 的 API Key）。",
    },
  ]);

  const canSend = useMemo(() => input.trim().length > 0 && !busy, [input, busy]);

  async function onSend() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    setInput("");
    const next = [...messages, { role: "user", content: text } as ChatMessage];
    setMessages(next);
    try {
      const resp = await postChat(next);
      setMessages([...next, { role: "assistant", content: resp.content }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMessages(next);
    } finally {
      setBusy(false);
    }
  }

  async function onIngestToday() {
    setError(null);
    setBusy(true);
    try {
      const d = todayStr();
      const r = await ingestFootballData(d, d);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `已导入 ${r.inserted_or_updated} 条比赛数据（${r.date_from} ~ ${r.date_to}）。`,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <section className="rounded-xl border border-zinc-200 bg-white">
        <div className="border-b border-zinc-200 px-4 py-3">
          <div className="text-sm font-semibold">对话</div>
          <div className="text-xs text-zinc-500">后端：FastAPI `/api/chat`（支持工具调用）</div>
        </div>
        <div className="h-[60vh] overflow-auto px-4 py-4">
          <div className="flex flex-col gap-3">
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={
                  m.role === "user"
                    ? "flex justify-end"
                    : "flex justify-start"
                }
              >
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[85%] whitespace-pre-wrap rounded-2xl bg-zinc-900 px-4 py-2 text-sm text-white"
                      : "max-w-[85%] whitespace-pre-wrap rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-sm text-zinc-900"
                  }
                >
                  {m.content}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="border-t border-zinc-200 p-3">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSend();
              }}
              placeholder="例如：今天有什么比赛？给我胜平负概率"
              className="flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
            />
            <button
              disabled={!canSend}
              onClick={onSend}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              发送
            </button>
          </div>
          {error ? <div className="mt-2 text-xs text-red-600">{error}</div> : null}
        </div>
      </section>

      <aside className="grid gap-3">
        <div className="rounded-xl border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">快捷操作</div>
          <div className="mt-2 grid gap-2">
            <button
              onClick={onIngestToday}
              disabled={busy}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
            >
              导入今日五大联赛赛程
            </button>
            <button
              onClick={() => setInput("今天有什么比赛？")}
              disabled={busy}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
            >
              填入：今天有什么比赛？
            </button>
            <button
              onClick={() => setInput("给我今天五大联赛的胜平负概率，并列出关键因素")}
              disabled={busy}
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
            >
              填入：今日胜平负概率
            </button>
          </div>
          <div className="mt-3 text-xs text-zinc-500">
            若导入失败，检查后端 `football-predictor/.env` 中是否配置 `FOOTBALL_DATA_API_KEY`。
          </div>
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-4">
          <div className="text-sm font-semibold">P0 说明</div>
          <div className="mt-2 text-xs text-zinc-600 leading-5">
            预测模型为泊松基线：使用两队近期已结束比赛的场均进失球估计期望进球，再计算胜平负概率。
          </div>
        </div>
      </aside>
    </div>
  );
}

