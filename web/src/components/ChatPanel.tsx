"use client";

import { useMemo, useState } from "react";
import type { ChatContext, ChatMessage } from "@/lib/api";
import { postChat } from "@/lib/api";
import { ActionButton, SurfaceCard } from "@/components/Workbench";

type Props = {
  mode?: "standalone" | "embedded";
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

// 快捷提问：低饱和的次要按钮，不做成卡片。
const PROMPT_CLASS =
  "w-full rounded-md border border-zinc-200 px-3 py-2 text-left text-xs text-zinc-600 transition hover:bg-zinc-50 hover:text-zinc-900 disabled:cursor-not-allowed disabled:opacity-50";

const INPUT_CLASS =
  "flex-1 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400";

function MessageList({ messages, heightClassName }: { messages: ChatMessage[]; heightClassName: string }) {
  return (
    <div className={`${heightClassName} overflow-auto`}>
      <div className="flex flex-col gap-3">
        {messages.map((m, idx) => (
          <div key={idx} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[85%] whitespace-pre-wrap rounded-lg bg-zinc-900 px-3.5 py-2.5 text-sm text-white"
                  : "max-w-[85%] whitespace-pre-wrap rounded-lg border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-900"
              }
            >
              {m.content}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChatPanel(props: Props) {
  const {
    mode = "standalone",
    heightClassName = "h-[58vh]",
    title = "对话区",
    description = "适合做自然语言查询、解释和操作建议。",
    initialMessages,
    quickPrompts = [],
    rightTitle = "快捷提问",
    rightDescription = "点击填入输入框，再发送。",
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

  const inputRow = (
    <div className="mt-3 flex gap-2">
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSend();
        }}
        placeholder="例如：解释 2026-09-02 的总控计划与执行差异"
        className={INPUT_CLASS}
      />
      <ActionButton disabled={!canSend} onClick={onSend}>
        发送
      </ActionButton>
    </div>
  );

  if (mode === "embedded") {
    return (
      <div className="grid gap-3">
        <MessageList messages={messages} heightClassName={heightClassName} />
        {inputRow}
        {error ? <div className="text-xs text-red-600">{error}</div> : null}
        {quickPrompts.length > 0 ? (
          <div className="grid gap-2">
            <div className="text-xs text-zinc-500">快捷提问</div>
            <div className="grid gap-2">
              {quickPrompts.map((prompt) => (
                <button key={prompt} onClick={() => setInput(prompt)} disabled={busy} className={PROMPT_CLASS}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <SurfaceCard title={title} description={description}>
        <MessageList messages={messages} heightClassName={heightClassName} />
        {inputRow}
        {error ? <div className="mt-2 text-xs text-red-600">{error}</div> : null}
      </SurfaceCard>

      <SurfaceCard title={rightTitle} description={rightDescription}>
        {extraRightTop}
        <div className="grid gap-2">
          {quickPrompts.map((prompt) => (
            <button key={prompt} onClick={() => setInput(prompt)} disabled={busy} className={PROMPT_CLASS}>
              {prompt}
            </button>
          ))}
        </div>
        {!quickPrompts.length ? <div className="text-xs text-zinc-500">暂无快捷提问。</div> : null}
      </SurfaceCard>
    </div>
  );
}
