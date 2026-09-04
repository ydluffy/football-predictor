"use client";

import { useState } from "react";
import { ActionButton, StatusBadge } from "@/components/Workbench";
import { clearStoredAuth, setStoredAuth, getStoredAuthBase64 } from "@/lib/workbenchClientAuth";

type Props = {
  title?: string;
  description?: string;
  onSuccess?: () => void;
};

export function WorkbenchLoginInline(props: Props) {
  const {
    title = "管理员登录",
    description = "该区域启用了工作台管理员认证。请输入你在 Vercel 配置的 WORKBENCH_ADMIN_USER / WORKBENCH_ADMIN_PASSWORD。",
    onSuccess,
  } = props;

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState<string>("");

  const hasStored = Boolean(getStoredAuthBase64());

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-zinc-950">{title}</div>
          <div className="mt-1 text-xs text-zinc-600">{description}</div>
        </div>
        <StatusBadge tone={hasStored ? "success" : "warning"}>{hasStored ? "已保存凭证" : "未登录"}</StatusBadge>
      </div>

      {msg ? <div className="mt-2 text-xs text-zinc-700 whitespace-pre-wrap">{msg}</div> : null}

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="grid gap-1 text-xs text-zinc-600">
          <span>用户名</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="WORKBENCH_ADMIN_USER"
            className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
          />
        </label>
        <label className="grid gap-1 text-xs text-zinc-600">
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="WORKBENCH_ADMIN_PASSWORD"
            className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <ActionButton
          onClick={() => {
            if (!username.trim() || !password) {
              setMsg("请先填写用户名和密码。");
              return;
            }
            setStoredAuth(username, password);
            setMsg("✅ 已保存登录凭证（仅保存在浏览器本地存储中）。现在可以重试页面操作。");
            onSuccess?.();
          }}
        >
          保存并重试
        </ActionButton>

        <ActionButton
          tone="secondary"
          onClick={() => {
            clearStoredAuth();
            setMsg("已清除本地保存的凭证。");
            onSuccess?.();
          }}
        >
          退出/清除
        </ActionButton>
      </div>

      <div className="mt-3 text-xs text-zinc-500">
        说明：当前认证是 HTTP Basic，网页本身不保存服务器端 session。这里采用“前端为请求附带 Authorization 头”的方式，让你能在页面内完成登录。
      </div>
    </section>
  );
}

