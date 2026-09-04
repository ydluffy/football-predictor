"use client";

import { useMemo, useState } from "react";
import type { ChatContext, ChatMessage } from "@/lib/api";
import { postChat } from "@/lib/api";
import { ActionButton, MetricCard, SurfaceCard } from "@/components/Workbench";

type Props = {
  mode?: "standalone" | "embedded";
  showMetrics?: boolean;
  heightClassName?: string;
  title?: string;
  description?: string;
  initialMessages?: ChatMessage[];
  quickPrompts?: string[];
  rightTitle?: string;
  rightDescription?: string;
  extraRightTop?: React.ReactNode;
  context?: ChatContext;
};

export function ChatPanel(props: Props) {
  const {
    mode = "standalone",
    showMetrics = true,
    heightClassName = "h-[58vh]",
    title = "对话区",
    description = "后端：`/api/chat`。适合做自然语言查询、解释和操作建议。",
    initialMessages,
    quickPrompts = [],
    rightTitle = "快捷提问",
    rightDescription = "把常用追问集中在这里。",
    extraRightTop,
    context,
  } = props;

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(
    initialMessages?.length
      ? initialMessages
      : [
          {
            role: "assistant",
            content:
              "你好，我是你的 AI 助手。\n\n你可以直接描述你想看什么（例如：解释今日总控计划、对比基线与终版、找出需要关注的比赛）。",
          },
        ],
  );

  const canSend = useMemo(() => input.trim().length > 0 && !busy, [input, busy]);
  const userMessageCount = useMemo(() => messages.filter((m) => m.role === "user").length, [messages]);
  const assistantMessageCount = useMemo(() => messages.filter((m) => m.role === "assistant").length, [messages]);

  async function onSend() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    setBusy(true);
    setInput("");
    const next = [...messages, { role: "user", content: text } as ChatMessage];
    setMessages(next);
    try {
      const resp = await postChat(next, context);
      setMessages([...next, { role: "assistant", content: resp.content }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMessages(next);
    } finally {
      setBusy(false);
    }
  }

  const metricsBlock =
    showMetrics && mode === "standalone" ? (
      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard label="总消息" value={String(messages.length)} hint="当前会话中的消息总数" />
        <MetricCard label="用户提问" value={String(userMessageCount)} hint="已发送的用户消息数" />
        <MetricCard label="助手回复" value={String(assistantMessageCount)} hint="当前助手回复次数" />
      </section>
    ) : null;

  const chatBody = (
    <>
      <div className={mode === "embedded" ? `${heightClassName} overflow-auto rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-3` : `${heightClassName} overflow-auto`}>
        <div className="flex flex-col gap-3">
          {messages.map((m, idx) => (
            <div key={idx} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  m.role === "user"
                    ? "max-w-[85%] whitespace-pre-wrap rounded-2xl bg-zinc-900 px-4 py-3 text-sm text-white"
                    : "max-w-[85%] whitespace-pre-wrap rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900"
                }
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSend();
          }}
          placeholder="例如：解释 2026-09-02 的总控计划与执行差异"
          className="flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
        />
        <ActionButton disabled={!canSend} onClick={onSend}>
          发送
        </ActionButton>
      </div>
      {error ? <div className="mt-2 text-xs text-red-600">{error}</div> : null}
      {quickPrompts.length > 0 && mode === "embedded" ? (
        <div className="mt-3 grid gap-2">
          <div className="text-xs text-zinc-500">快捷提问</div>
          <div className="grid gap-2">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => setInput(prompt)}
                disabled={busy}
                className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );

  if (mode === "embedded") {
    return <div className="grid gap-3">{chatBody}</div>;
  }

  return (
    <div className="grid gap-6">
      {metricsBlock}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <SurfaceCard title={title} description={description}>
          <div className={heightClassName + " overflow-auto"}>
            <div className="flex flex-col gap-3">
              {messages.map((m, idx) => (
                <div key={idx} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[85%] whitespace-pre-wrap rounded-2xl bg-zinc-900 px-4 py-3 text-sm text-white"
                        : "max-w-[85%] whitespace-pre-wrap rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-900"
                    }
                  >
                    {m.content}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSend();
              }}
              placeholder="例如：解释 2026-09-02 的总控计划与执行差异"
              className="flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
            />
            <ActionButton disabled={!canSend} onClick={onSend}>
              发送
            </ActionButton>
          </div>
          {error ? <div className="mt-2 text-xs text-red-600">{error}</div> : null}
        </SurfaceCard>

        <aside className="grid gap-4">
          <SurfaceCard title={rightTitle} description={rightDescription}>
            {extraRightTop}
            <div className="grid gap-2">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => setInput(prompt)}
                  disabled={busy}
                  className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
            {!quickPrompts.length ? <div className="text-xs text-zinc-500">暂无快捷提问。</div> : null}
          </SurfaceCard>
        </aside>
      </div>
    </div>
  );
}
