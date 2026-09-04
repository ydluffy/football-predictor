"use client";

import { useEffect, useMemo, useState } from "react";
import { ActionButton, PageIntro, StatusBadge, SurfaceCard } from "@/components/Workbench";
import { ChatPanel } from "@/components/ChatPanel";
import { WorkbenchLoginInline } from "@/components/WorkbenchLoginInline";
import { getShanghaiToday } from "@/lib/time";
import { workbenchFetch } from "@/lib/workbenchClientAuth";

type ControllerStatusResponse = {
  controller_state: any | null;
  sales_day: string | null;
  daily_override: any | null;
  task_registry: any | null;
  error?: string;
};

type LlmConfigSummary = {
  id: string;
  label: string;
  provider: string;
  base_url: string;
  model: string;
  created_at?: string;
  updated_at?: string;
};

type LlmConfigListResponse = {
  active_config_id: string | null;
  configs: LlmConfigSummary[];
  error?: string;
};

function toSalesDay(d: Date) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export default function ControllerPage() {
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string>("");
  const [salesDay, setSalesDay] = useState(getShanghaiToday());
  const [data, setData] = useState<ControllerStatusResponse | null>(null);
  const [needAuth, setNeedAuth] = useState(false);

  const [llmLoading, setLlmLoading] = useState(false);
  const [llmMsg, setLlmMsg] = useState<string>("");
  const [llmActiveId, setLlmActiveId] = useState<string | null>(null);
  const [llmConfigs, setLlmConfigs] = useState<LlmConfigSummary[]>([]);
  const [newCfg, setNewCfg] = useState({ label: "", base_url: "", model: "", api_key: "", provider: "ark" });

  const providerPresets = useMemo(() => {
    return {
      ark: {
        label: "火山方舟（Coding Plan）",
        base_url: "https://ark.cn-beijing.volces.com/api/coding/v3",
        modelHint:
          "示例：ark-code-latest 或 deepseek-v4-pro 等（以 Coding Plan 企业版页面支持的模型名为准）。如果你用的是“方舟平台 API Key（非 Coding Plan 专属）”，base_url 通常改用 https://ark.cn-beijing.volces.com/api/v3。",
      },
      deepseek: {
        label: "DeepSeek",
        base_url: "https://api.deepseek.com",
        modelHint: "示例：deepseek-chat / deepseek-reasoner（以 DeepSeek 控制台为准）",
      },
      qwen: {
        label: "通义千问（百炼/DashScope）",
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        modelHint: "示例：qwen-plus / qwen-turbo（以百炼控制台为准；部分地域需替换为你的 WorkspaceId 域名）",
      },
      openai_compatible: {
        label: "自定义网关",
        base_url: "",
        modelHint: "示例：填你的网关所需的模型名",
      },
    } as const;
  }, []);

  useEffect(() => {
    // provider 切换时，自动填充推荐 base_url（但不覆盖用户已输入的自定义值）
    const preset = (providerPresets as any)[newCfg.provider];
    if (!preset) return;
    setNewCfg((s) => {
      if (String(s.base_url || "").trim()) return s;
      return { ...s, base_url: preset.base_url };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newCfg.provider]);

  const yesterday = useMemo(() => {
    const d = new Date(`${salesDay}T00:00:00+08:00`);
    const prev = new Date(d.getTime() - 24 * 3600 * 1000);
    return toSalesDay(prev);
  }, [salesDay]);

  async function refresh(targetDay = salesDay) {
    setLoading(true);
    setMsg("");
    try {
      const r = await workbenchFetch(`/api/automation/status?sales_day=${encodeURIComponent(targetDay)}`, { cache: "no-store" });
      const raw = await r.text();
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      const j = (raw && raw.trim().startsWith("{") ? JSON.parse(raw) : null) as ControllerStatusResponse | null;
      if (!r.ok) throw new Error((j as any)?.error || `HTTP ${r.status}: ${raw.slice(0, 120)}`);
      if (!j) throw new Error(`非 JSON 响应：${raw.slice(0, 120)}`);
      setData(j);
    } catch (e) {
      setMsg(`❌ 加载失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function syncDays(days: string[]) {
    setLoading(true);
    setMsg("");
    try {
      const r = await workbenchFetch("/api/automation/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sales_days: days }),
      });
      const t = await r.text();
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
      setMsg(`✅ 同步完成：${t}`);
      await refresh(days[0] || salesDay);
    } catch (e) {
      setMsg(`❌ 同步失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    refreshLlmConfigs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshLlmConfigs() {
    setLlmLoading(true);
    setLlmMsg("");
    try {
      const r = await workbenchFetch("/api/llm-config", { cache: "no-store" });
      const raw = await r.text();
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      const j = (raw && raw.trim().startsWith("{") ? JSON.parse(raw) : null) as LlmConfigListResponse | null;
      if (!r.ok) throw new Error((j as any)?.error || `HTTP ${r.status}: ${raw.slice(0, 120)}`);
      if (!j) throw new Error(`非 JSON 响应：${raw.slice(0, 120)}`);
      setLlmConfigs(Array.isArray(j.configs) ? j.configs : []);
      setLlmActiveId(j.active_config_id || null);
    } catch (e) {
      setLlmMsg(`❌ 模型配置加载失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLlmLoading(false);
    }
  }

  async function setActiveConfig(id: string | null) {
    setLlmLoading(true);
    setLlmMsg("");
    try {
      const r = await workbenchFetch("/api/llm-config/active", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_config_id: id }),
      });
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      const j = (await r.json().catch(() => ({}))) as any;
      if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
      setLlmActiveId(id);
      setLlmMsg(id ? "✅ 已切换启用模型配置。" : "✅ 已关闭模型配置（仅系统能力回答）。");
    } catch (e) {
      setLlmMsg(`❌ 切换失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLlmLoading(false);
    }
  }

  async function createConfig() {
    setLlmLoading(true);
    setLlmMsg("");
    try {
      const r = await workbenchFetch("/api/llm-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newCfg),
      });
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      const j = (await r.json().catch(() => ({}))) as any;
      if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
      setNewCfg({ label: "", base_url: "", model: "", api_key: "", provider: "ark" });
      setLlmMsg("✅ 已新增模型配置（并在未设置 active 时自动启用）。");
      await refreshLlmConfigs();
    } catch (e) {
      setLlmMsg(`❌ 新增失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLlmLoading(false);
    }
  }

  async function deleteConfig(id: string) {
    if (!confirm("确定删除该模型配置？（不会回显 API Key，删除后不可恢复）")) return;
    setLlmLoading(true);
    setLlmMsg("");
    try {
      const r = await workbenchFetch(`/api/llm-config/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      const j = (await r.json().catch(() => ({}))) as any;
      if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
      setLlmMsg("✅ 已删除模型配置。");
      await refreshLlmConfigs();
    } catch (e) {
      setLlmMsg(`❌ 删除失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLlmLoading(false);
    }
  }

  async function testActiveConfig() {
    setLlmLoading(true);
    setLlmMsg("");
    try {
      const r = await workbenchFetch("/api/llm-config/test", { method: "POST" });
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      const j = (await r.json().catch(() => ({}))) as any;
      setLlmMsg(j?.ok ? `✅ 测试通过：${j.latency_ms}ms` : `⚠️ 测试未通过：${j?.error || j?.status || "unknown"}`);
    } catch (e) {
      setLlmMsg(`❌ 测试失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLlmLoading(false);
    }
  }

  const controller = data?.controller_state || null;
  const override = data?.daily_override?.payload || data?.daily_override || null;
  const registry = data?.task_registry?.payload || data?.task_registry || null;

  const overrideTasks: any[] = useMemo(() => {
    const arr = override?.tasks;
    return Array.isArray(arr) ? arr : [];
  }, [override]);

  const registryTasks: any[] = useMemo(() => {
    const arr = registry?.tasks;
    return Array.isArray(arr) ? arr : [];
  }, [registry]);

  const registryStats = useMemo(() => {
    const stats = { completed: 0, scheduled: 0, failed: 0, other: 0 };
    for (const t of registryTasks) {
      const s = String(t?.status || "").toLowerCase();
      if (s === "completed") stats.completed += 1;
      else if (s === "scheduled") stats.scheduled += 1;
      else if (s === "failed") stats.failed += 1;
      else stats.other += 1;
    }
    return stats;
  }, [registryTasks]);

  const controllerSummary = useMemo(() => {
    if (!controller) return { status: "未知", tone: "neutral" as const };
    const s = String(controller.status || "").toLowerCase();
    if (s === "active") return { status: "运行中", tone: "success" as const };
    if (s) return { status: controller.status, tone: "warning" as const };
    return { status: "未知", tone: "neutral" as const };
  }, [controller]);

  const assistantQuickPrompts = useMemo(() => {
    const sd = salesDay;
    return [
      `读取销售日 ${sd} 的总控计划与执行状态，并总结：有哪些阶段、每个阶段的目标、哪些已完成/待执行。`,
      `读取销售日 ${sd} 的 override 与 registry，找出差异（例如：计划有但未执行、执行失败、硬锁/截止风险），并给出处理建议。`,
      `读取销售日 ${sd} 的总控信息，按“基线→终版对比”列出需要重点记录的快照字段（体彩赔率、让球、外盘让球线与水位等）。`,
      `读取销售日 ${sd} 的总控任务，帮我把它转成网站页面上的“调度摘要”（用于用户快速理解）。`,
    ];
  }, [salesDay]);

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="总控"
        title="总控助手"
        description="把“同步 + 状态摘要 + 解释建议”收进一个卡片里。需要更多细节时再展开查看。"
      />

      {needAuth ? (
        <WorkbenchLoginInline
          onSuccess={() => {
            setNeedAuth(false);
            refresh();
            refreshLlmConfigs();
          }}
        />
      ) : null}

      {msg ? (
        <section className="rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-700 shadow-sm">
          <pre className="whitespace-pre-wrap font-sans">{msg}</pre>
        </section>
      ) : null}

      <SurfaceCard
        title="总控助手（一个板块）"
        description="建议使用方式：先同步 → 再让助手解释差异/风险 → 必要时展开细节。"
        action={
          <div className="flex flex-wrap gap-2">
            <ActionButton tone="secondary" onClick={() => refresh()} disabled={loading}>
              {loading ? "刷新中…" : "刷新"}
            </ActionButton>
            <ActionButton tone="secondary" onClick={() => syncDays([salesDay, yesterday])} disabled={loading}>
              {loading ? "同步中…" : "同步今日+昨日"}
            </ActionButton>
          </div>
        }
      >
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>sales_day</span>
              <input
                type="date"
                value={salesDay}
                onChange={(e) => setSalesDay(e.target.value)}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <ActionButton onClick={() => refresh(salesDay)} disabled={loading}>
              查看该日
            </ActionButton>
            <ActionButton tone="secondary" onClick={() => syncDays([salesDay])} disabled={loading}>
              同步该日
            </ActionButton>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <StatusBadge tone={controllerSummary.tone}>控制器：{controllerSummary.status}</StatusBadge>
            <StatusBadge tone={overrideTasks.length > 0 ? "success" : "warning"}>计划：{overrideTasks.length} 阶段</StatusBadge>
            <StatusBadge tone={registryTasks.length > 0 ? "success" : "warning"}>执行：{registryTasks.length} 任务</StatusBadge>
            {registryStats.failed > 0 ? <StatusBadge tone="danger">失败：{registryStats.failed}</StatusBadge> : null}
            {registryStats.scheduled > 0 ? <StatusBadge tone="neutral">待跑：{registryStats.scheduled}</StatusBadge> : null}
            {registryStats.completed > 0 ? <StatusBadge tone="success">已完成：{registryStats.completed}</StatusBadge> : null}
          </div>

          <ChatPanel
            mode="embedded"
            showMetrics={false}
            heightClassName="h-[42vh]"
            context={{ page: "controller", sales_day: salesDay }}
            initialMessages={[
              {
                role: "assistant",
                content:
                  "你可以直接问我当前销售日的“计划 vs 执行差异”、hard_lock 风险、以及基线→终版该怎么对比。\n\n我会先读取总控数据再回答。",
              },
            ]}
            quickPrompts={assistantQuickPrompts}
          />

          <details className="rounded-xl border border-zinc-200 bg-white px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-zinc-900">模型配置（BYOK，可选）</summary>
            <div className="mt-3 grid gap-3">
              <div className="text-xs text-zinc-600">
                说明：这里配置的是“总控助手”的大模型接口。球赛事实仍以系统数据为准；模型只负责表达、建议与追问。API Key 会在服务端加密存储，
                页面不会回显明文。若未配置模型，助手仍可回答系统类问题。
              </div>

              {llmMsg ? (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-700 whitespace-pre-wrap">{llmMsg}</div>
              ) : null}

              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={llmActiveId ? "success" : "warning"}>当前：{llmActiveId ? "已启用" : "未启用"}</StatusBadge>
                <ActionButton tone="secondary" onClick={() => refreshLlmConfigs()} disabled={llmLoading}>
                  {llmLoading ? "刷新中…" : "刷新配置"}
                </ActionButton>
                <ActionButton tone="secondary" onClick={() => testActiveConfig()} disabled={llmLoading}>
                  {llmLoading ? "测试中…" : "测试当前配置"}
                </ActionButton>
                <ActionButton tone="secondary" onClick={() => setActiveConfig(null)} disabled={llmLoading}>
                  关闭模型
                </ActionButton>
              </div>

              <div className="grid gap-2">
                <div className="text-xs font-medium text-zinc-700">已有配置</div>
                {llmConfigs.length === 0 ? (
                  <div className="text-xs text-zinc-500">暂无配置。你可以新增一个国内模型配置（方舟/DeepSeek/通义千问）或自定义网关。</div>
                ) : (
                  llmConfigs.map((c) => (
                    <div key={c.id} className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm text-zinc-950">
                            {c.label} {llmActiveId === c.id ? <span className="text-xs text-emerald-700">（已启用）</span> : null}
                          </div>
                          <div className="mt-1 text-xs text-zinc-600 break-all">
                            {c.provider} · {c.model} · {c.base_url}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <ActionButton tone="secondary" onClick={() => setActiveConfig(c.id)} disabled={llmLoading}>
                            启用
                          </ActionButton>
                          <ActionButton tone="secondary" onClick={() => deleteConfig(c.id)} disabled={llmLoading}>
                            删除
                          </ActionButton>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="grid gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-3">
                <div className="text-xs font-medium text-zinc-700">新增配置</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="grid gap-1 text-xs text-zinc-600">
                    <span>名称</span>
                    <input
                      value={newCfg.label}
                      onChange={(e) => setNewCfg((s) => ({ ...s, label: e.target.value }))}
                      placeholder="例如：豆包 Pro（自带 Key）"
                      className="rounded-lg border border-zinc-200 bg-white px-2 py-2 outline-none focus:border-zinc-400"
                    />
                  </label>
                  <label className="grid gap-1 text-xs text-zinc-600">
                    <span>模型名（model）</span>
                    <input
                      value={newCfg.model}
                      onChange={(e) => setNewCfg((s) => ({ ...s, model: e.target.value }))}
                      placeholder="例如：doubao-seed-xxx / deepseek-chat / qwen-plus"
                      className="rounded-lg border border-zinc-200 bg-white px-2 py-2 outline-none focus:border-zinc-400"
                    />
                  </label>
                </div>
                <label className="grid gap-1 text-xs text-zinc-600">
                  <span>模型平台（provider）</span>
                  <select
                    value={newCfg.provider}
                    onChange={(e) => setNewCfg((s) => ({ ...s, provider: e.target.value }))}
                    className="rounded-lg border border-zinc-200 bg-white px-2 py-2 outline-none focus:border-zinc-400"
                  >
                    <option value="ark">火山方舟</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="qwen">通义千问</option>
                    <option value="openai_compatible">自定义网关</option>
                  </select>
                </label>
                <label className="grid gap-1 text-xs text-zinc-600">
                  <span>base_url（按平台实际填写）</span>
                  <input
                    value={newCfg.base_url}
                    onChange={(e) => setNewCfg((s) => ({ ...s, base_url: e.target.value }))}
                    placeholder="例如：https://ark.cn-beijing.volces.com/api/coding/v3 或 https://api.deepseek.com 或 https://dashscope.aliyuncs.com/compatible-mode/v1"
                    className="rounded-lg border border-zinc-200 bg-white px-2 py-2 outline-none focus:border-zinc-400"
                  />
                </label>
                <label className="grid gap-1 text-xs text-zinc-600">
                  <span>API Key（仅保存，不回显）</span>
                  <input
                    type="password"
                    value={newCfg.api_key}
                    onChange={(e) => setNewCfg((s) => ({ ...s, api_key: e.target.value }))}
                    placeholder="sk-*** 或国内厂商 key"
                    className="rounded-lg border border-zinc-200 bg-white px-2 py-2 outline-none focus:border-zinc-400"
                  />
                </label>
                <div className="flex flex-wrap items-center gap-2">
                  <ActionButton onClick={() => createConfig()} disabled={llmLoading}>
                    {llmLoading ? "提交中…" : "新增并保存"}
                  </ActionButton>
                  <div className="text-xs text-zinc-500">
                    提示：若服务端未配置 `APP_ENCRYPTION_KEY`，保存会失败。请先在 `web/.env.local`（或线上环境变量）配置该值并重启服务。
                  </div>
                </div>
                <div className="text-xs text-zinc-500">
                  推荐：{(providerPresets as any)[newCfg.provider]?.label} 默认 base_url 会自动填充。{(providerPresets as any)[newCfg.provider]?.modelHint}
                </div>
              </div>
            </div>
          </details>

          <details className="rounded-xl border border-zinc-200 bg-white px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-zinc-900">Repo Agent（规划中）</summary>
            <div className="mt-3 grid gap-3 text-sm text-zinc-700">
              <div className="text-xs text-zinc-600">
                目标：让“总控助手”未来具备类似 Codex 的仓库工作能力（读代码、提出变更、产出 patch、跑校验），但先按你当前决定，走可运营的“云端
                Agent 模式”，不直接访问本地磁盘。
              </div>

              <div className="grid gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-3 text-xs text-zinc-700">
                <div className="font-medium text-zinc-800">能力契约（先占位，暂不执行）</div>
                <ul className="list-disc pl-5">
                  <li>
                    上下文字段：<span className="font-mono">sales_day</span>（已启用）、<span className="font-mono">repo_snapshot_id</span>（预留）、
                    <span className="font-mono">pipeline_run_id</span>（预留）
                  </li>
                  <li>
                    未来工具集（云端沙箱）：<span className="font-mono">search_code</span> / <span className="font-mono">read_file</span> /{" "}
                    <span className="font-mono">propose_patch</span> / <span className="font-mono">apply_patch</span> /{" "}
                    <span className="font-mono">run_verify</span>
                  </li>
                  <li>安全边界：所有写入必须可审计、可回滚；默认先展示 diff，再确认应用。</li>
                </ul>
              </div>

              <div className="grid gap-2">
                <div className="text-xs font-medium text-zinc-700">当前状态</div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <StatusBadge tone="warning">未启用</StatusBadge>
                  <StatusBadge tone="neutral">repo_snapshot_id：—</StatusBadge>
                </div>
                <div className="text-xs text-zinc-500">
                  说明：现在的对话仍以“系统事实接口”为主（总控/赛程/预测/复盘）。Repo Agent 将在后续通过仓库快照/镜像接入，避免直接触达本地文件系统。
                </div>
              </div>
            </div>
          </details>

          <details className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-zinc-900">展开查看总控细节（计划/执行）</summary>
            <div className="mt-3 grid gap-4 xl:grid-cols-2">
              <div className="grid gap-2">
                <div className="text-xs font-medium text-zinc-700">Override（计划）</div>
                {overrideTasks.length === 0 ? (
                  <div className="text-xs text-zinc-500">暂无 override。</div>
                ) : (
                  overrideTasks.map((t) => (
                    <div key={String(t.key || t.run_at)} className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
                      <div className="text-sm text-zinc-950">{String(t.key || "未命名任务")}</div>
                      <div className="mt-1 text-xs text-zinc-500">
                        {String(t.run_at || "—")} · {String(t.stage_type || "—")}
                      </div>
                      {t.scope ? <div className="mt-1 text-xs text-zinc-600 line-clamp-2">{String(t.scope)}</div> : null}
                    </div>
                  ))
                )}
              </div>
              <div className="grid gap-2">
                <div className="text-xs font-medium text-zinc-700">Registry（执行）</div>
                {registryTasks.length === 0 ? (
                  <div className="text-xs text-zinc-500">暂无 registry。</div>
                ) : (
                  registryTasks.map((t) => {
                    const status = String(t.status || "unknown");
                    const tone =
                      status === "completed"
                        ? "success"
                        : status === "scheduled"
                          ? "neutral"
                          : status === "failed"
                            ? "danger"
                            : "warning";
                    return (
                      <div key={String(t.key || t.run_at)} className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm text-zinc-950">{String(t.task_name || t.key || "未命名任务")}</div>
                          <StatusBadge tone={tone as any}>{status}</StatusBadge>
                        </div>
                        <div className="mt-1 text-xs text-zinc-500">
                          run_at {String(t.run_at || "—")}
                          {t.hard_lock ? ` · lock ${String(t.hard_lock)}` : ""}
                          {t.sales_cutoff ? ` · cutoff ${String(t.sales_cutoff)}` : ""}
                        </div>
                        {t.last_error ? <div className="mt-1 text-xs text-red-700 line-clamp-2">{String(t.last_error)}</div> : null}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </details>
        </div>
      </SurfaceCard>
    </div>
  );
}
