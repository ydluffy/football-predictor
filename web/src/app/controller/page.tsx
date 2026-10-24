"use client";

import { useEffect, useMemo, useState } from "react";
import { ActionButton, PageIntro, StatStrip, StatusBadge, SurfaceCard } from "@/components/Workbench";
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

function relativeTime(iso: string) {
  const at = Date.parse(iso);
  if (!Number.isFinite(at)) return null;
  const minutes = Math.floor(Math.max(0, Date.now() - at) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
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

  // 同步健康度：页面只读 Supabase，这里要能一眼看出数据是不是已经真的上来了。
  const syncHealth = useMemo(() => {
    const last = controller?.last_sync;
    if (!last || typeof last.at !== "string") return null;
    const pending = Number(last.pending_count ?? (Array.isArray(last.pending_keys) ? last.pending_keys.length : 0)) || 0;
    const at = Date.parse(last.at);
    const ageHours = Number.isFinite(at) ? (Date.now() - at) / 3600000 : 0;
    const stale = Number.isFinite(at) && ageHours > 36;
    const ok = Boolean(last.ok) && pending === 0 && !stale;
    const tone = stale ? ("danger" as const) : pending > 0 || !last.ok ? ("warning" as const) : ("success" as const);
    return {
      label: relativeTime(last.at) || last.at,
      ok,
      tone,
      pending,
      reason: typeof last.last_failure_reason === "string" ? last.last_failure_reason : null,
      stage: typeof last.stage === "string" ? last.stage : null,
      webStarted: Boolean(last.web_started_by_sync),
    };
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

  const dataGapHint = useMemo(() => {
    if (controller || overrideTasks.length > 0 || registryTasks.length > 0) return null;
    return "当前销售日还没有可展示的总控数据。通常不是页面故障，而是 Supabase 里尚未写入 controller_state / override / registry。先点“同步该日”或在本地执行一次回填。";
  }, [controller, overrideTasks.length, registryTasks.length]);

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="总控"
        title="销售日总控"
        description="同步总控数据，再让助手解释“计划 vs 执行”的差异与风险。"
        actions={
          <>
            <ActionButton tone="secondary" onClick={() => refresh()} disabled={loading}>
              {loading ? "刷新中…" : "刷新"}
            </ActionButton>
            <ActionButton tone="secondary" onClick={() => syncDays([salesDay, yesterday])} disabled={loading}>
              {loading ? "同步中…" : "同步今日 + 昨日"}
            </ActionButton>
          </>
        }
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
        <section className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600">
          <pre className="whitespace-pre-wrap font-sans">{msg}</pre>
        </section>
      ) : null}

      <SurfaceCard title="总控助手">
        <div className="grid gap-4">
          <div className="flex flex-wrap items-end gap-2">
            <label className="grid gap-1.5 text-xs text-zinc-600">
              <span>销售日</span>
              <input
                type="date"
                value={salesDay}
                onChange={(e) => setSalesDay(e.target.value)}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
              />
            </label>
            <ActionButton onClick={() => refresh(salesDay)} disabled={loading}>
              查看该日
            </ActionButton>
            <ActionButton tone="secondary" onClick={() => syncDays([salesDay])} disabled={loading}>
              同步该日
            </ActionButton>
          </div>

          <StatStrip
            columns={4}
            items={[
              { label: "控制器", value: controllerSummary.status, tone: controllerSummary.tone },
              {
                label: "计划",
                value: `${overrideTasks.length} 阶段`,
                tone: overrideTasks.length > 0 ? "success" : "warning",
              },
              {
                label: "执行",
                value: `${registryTasks.length} 任务`,
                hint: `完成 ${registryStats.completed} · 待跑 ${registryStats.scheduled}`,
                tone: registryTasks.length > 0 ? "success" : "warning",
              },
              {
                label: "失败",
                value: String(registryStats.failed),
                tone: registryStats.failed > 0 ? "danger" : undefined,
              },
            ]}
          />

          {syncHealth ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
              <StatusBadge tone={syncHealth.tone}>{syncHealth.ok ? "同步正常" : "同步需注意"}</StatusBadge>
              <span>上次同步：{syncHealth.label}</span>
              {syncHealth.stage ? <span>阶段 {syncHealth.stage}</span> : null}
              {syncHealth.pending > 0 ? <span className="text-amber-600">待补偿 {syncHealth.pending}</span> : null}
              {syncHealth.reason ? <span className="text-red-600">最近失败：{syncHealth.reason}</span> : null}
              {syncHealth.webStarted ? <span>Web 由脚本自拉起</span> : null}
            </div>
          ) : (
            <div className="text-xs text-zinc-400">尚无同步健康度：本地跑一次阶段同步后自动出现。</div>
          )}

          {dataGapHint ? (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">{dataGapHint}</div>
          ) : null}

          <ChatPanel
            mode="embedded"
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

          <details className="border-t border-zinc-100 pt-3">
            <summary className="cursor-pointer text-sm font-medium text-zinc-900">模型配置（BYOK，可选）</summary>
            <div className="mt-3 grid gap-3">
              <div className="text-xs text-zinc-500">
                配置“总控助手”使用的大模型。球赛事实仍以系统数据为准，模型只负责表达与建议。API Key 服务端加密存储，页面不回显明文。
              </div>

              {llmMsg ? <div className="whitespace-pre-wrap text-xs text-zinc-600">{llmMsg}</div> : null}

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

              <div>
                <div className="text-xs text-zinc-500">已有配置</div>
                {llmConfigs.length === 0 ? (
                  <div className="mt-1 text-xs text-zinc-400">暂无配置，可在下方新增。</div>
                ) : (
                  <div className="mt-1 divide-y divide-zinc-100">
                    {llmConfigs.map((c) => (
                      <div key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0">
                        <div className="min-w-0">
                          <div className="text-sm text-zinc-900">
                            {c.label}
                            {llmActiveId === c.id ? <span className="ml-1 text-xs text-emerald-600">已启用</span> : null}
                          </div>
                          <div className="mt-0.5 break-all text-xs text-zinc-500">
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
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-2 border-t border-zinc-100 pt-3">
                <div className="text-xs text-zinc-500">新增配置</div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="grid gap-1 text-xs text-zinc-600">
                    <span>名称</span>
                    <input
                      value={newCfg.label}
                      onChange={(e) => setNewCfg((s) => ({ ...s, label: e.target.value }))}
                      placeholder="例如：豆包 Pro（自带 Key）"
                      className="rounded-md border border-zinc-200 bg-white px-2.5 py-2 outline-none focus:border-zinc-400"
                    />
                  </label>
                  <label className="grid gap-1 text-xs text-zinc-600">
                    <span>模型名（model）</span>
                    <input
                      value={newCfg.model}
                      onChange={(e) => setNewCfg((s) => ({ ...s, model: e.target.value }))}
                      placeholder="例如：doubao-seed-xxx / deepseek-chat / qwen-plus"
                      className="rounded-md border border-zinc-200 bg-white px-2.5 py-2 outline-none focus:border-zinc-400"
                    />
                  </label>
                </div>
                <label className="grid gap-1 text-xs text-zinc-600">
                  <span>模型平台（provider）</span>
                  <select
                    value={newCfg.provider}
                    onChange={(e) => setNewCfg((s) => ({ ...s, provider: e.target.value }))}
                    className="rounded-md border border-zinc-200 bg-white px-2.5 py-2 outline-none focus:border-zinc-400"
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
                    className="rounded-md border border-zinc-200 bg-white px-2.5 py-2 outline-none focus:border-zinc-400"
                  />
                </label>
                <label className="grid gap-1 text-xs text-zinc-600">
                  <span>API Key（仅保存，不回显）</span>
                  <input
                    type="password"
                    value={newCfg.api_key}
                    onChange={(e) => setNewCfg((s) => ({ ...s, api_key: e.target.value }))}
                    placeholder="sk-*** 或国内厂商 key"
                    className="rounded-md border border-zinc-200 bg-white px-2.5 py-2 outline-none focus:border-zinc-400"
                  />
                </label>
                <div className="flex flex-wrap items-center gap-3">
                  <ActionButton onClick={() => createConfig()} disabled={llmLoading}>
                    {llmLoading ? "提交中…" : "新增并保存"}
                  </ActionButton>
                  <div className="text-xs text-zinc-500">
                    推荐：{(providerPresets as any)[newCfg.provider]?.label} 默认 base_url 会自动填充。
                    {(providerPresets as any)[newCfg.provider]?.modelHint}
                  </div>
                </div>
                <div className="text-xs text-zinc-400">
                  若服务端未配置 APP_ENCRYPTION_KEY，保存会失败，需先在环境变量中配置并重启服务。
                </div>
              </div>
            </div>
          </details>

          <details className="border-t border-zinc-100 pt-3">
            <summary className="cursor-pointer text-sm font-medium text-zinc-900">总控细节（计划 / 执行）</summary>
            <div className="mt-3 grid gap-4 xl:grid-cols-2">
              <div>
                <div className="text-xs text-zinc-500">Override（计划）</div>
                {overrideTasks.length === 0 ? (
                  <div className="mt-1 text-xs text-zinc-400">暂无 override。</div>
                ) : (
                  <div className="mt-1 divide-y divide-zinc-100">
                    {overrideTasks.map((t) => (
                      <div key={String(t.key || t.run_at)} className="py-2.5 first:pt-0 last:pb-0">
                        <div className="text-sm text-zinc-900">{String(t.key || "未命名任务")}</div>
                        <div className="mt-0.5 text-xs text-zinc-500">
                          {String(t.run_at || "—")} · {String(t.stage_type || "—")}
                        </div>
                        {t.scope ? <div className="mt-0.5 line-clamp-2 text-xs text-zinc-600">{String(t.scope)}</div> : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <div className="text-xs text-zinc-500">Registry（执行）</div>
                {registryTasks.length === 0 ? (
                  <div className="mt-1 text-xs text-zinc-400">暂无 registry。</div>
                ) : (
                  <div className="mt-1 divide-y divide-zinc-100">
                    {registryTasks.map((t) => {
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
                        <div key={String(t.key || t.run_at)} className="py-2.5 first:pt-0 last:pb-0">
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-sm text-zinc-900">{String(t.task_name || t.key || "未命名任务")}</div>
                            <StatusBadge tone={tone as any}>{status}</StatusBadge>
                          </div>
                          <div className="mt-0.5 text-xs text-zinc-500">
                            run_at {String(t.run_at || "—")}
                            {t.hard_lock ? ` · lock ${String(t.hard_lock)}` : ""}
                            {t.sales_cutoff ? ` · cutoff ${String(t.sales_cutoff)}` : ""}
                          </div>
                          {t.last_error ? <div className="mt-0.5 line-clamp-2 text-xs text-red-600">{String(t.last_error)}</div> : null}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </details>
        </div>
      </SurfaceCard>
    </div>
  );
}
