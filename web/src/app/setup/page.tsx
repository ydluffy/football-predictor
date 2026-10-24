"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ActionButton,
  PageIntro,
  PrimaryLink,
  SecondaryLink,
  StatStrip,
  StatusBadge,
  SurfaceCard,
} from "@/components/Workbench";
import { WorkbenchLoginInline } from "@/components/WorkbenchLoginInline";
import { getShanghaiToday } from "@/lib/time";
import { workbenchFetch } from "@/lib/workbenchClientAuth";

type StatusResponse = {
  env: {
    hasSupabaseUrl: boolean;
    hasSupabaseServiceRole: boolean;
    hasFootballDataKey: boolean;
    hasOpenRouterKey: boolean;
    hasApiFootballKey?: boolean;
    openRouterModel: string | null;
  };
  supabase: {
    ok: boolean | null;
    fixturesCount: number | null;
    error: string | null;
  };
};

type BacktestResponse = {
  summary?: {
    n: number;
    accuracy: number | null;
    logloss: number | null;
    brier: number | null;
  };
  error?: string;
};

export default function SetupPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string>("");
  const [needAuth, setNeedAuth] = useState(false);
  const [dateFrom, setDateFrom] = useState(getShanghaiToday());
  const [dateTo, setDateTo] = useState(getShanghaiToday());
  const [oddsDate, setOddsDate] = useState(getShanghaiToday());
  const [snapshotDate, setSnapshotDate] = useState(getShanghaiToday());
  const [btFrom, setBtFrom] = useState(getShanghaiToday());
  const [btTo, setBtTo] = useState(getShanghaiToday());
  const [btResult, setBtResult] = useState<BacktestResponse | null>(null);

  async function refresh() {
    const r = await fetch("/api/status", { cache: "no-store" });
    const j = (await r.json()) as StatusResponse;
    setStatus(j);
  }

  useEffect(() => {
    refresh();
  }, []);

  // “系统能跑起来”的核心条件：仅依赖 Supabase（其余 key 视为可选能力）
  const coreEnvOk = useMemo(() => {
    if (!status) return false;
    return status.env.hasSupabaseUrl && status.env.hasSupabaseServiceRole;
  }, [status]);

  // 导入比赛数据（football-data.org）需要额外的 FOOTBALL_DATA_API_KEY
  const canIngestFootballData = useMemo(() => {
    if (!status) return false;
    return coreEnvOk && status.env.hasFootballDataKey;
  }, [status, coreEnvOk]);

  const envReadyCount = useMemo(() => {
    if (!status) return 0;
    return [
      status.env.hasSupabaseUrl,
      status.env.hasSupabaseServiceRole,
      status.env.hasFootballDataKey,
      status.env.hasOpenRouterKey,
      Boolean(status.env.hasApiFootballKey),
    ].filter(Boolean).length;
  }, [status]);

  async function ingest() {
    setLoading(true);
    setMsg("");
    try {
      const r = await workbenchFetch(
        `/api/ingest/football-data?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`,
        { method: "POST" },
      );
      const t = await r.text();
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
      setMsg(`✅ 导入成功：${t}`);
      await refresh();
    } catch (e) {
      setMsg(`❌ 导入失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function ingestOdds() {
    setLoading(true);
    setMsg("");
    try {
      const qs = new URLSearchParams({ date: oddsDate });
      const r = await workbenchFetch(`/api/ingest/odds?${qs.toString()}`, { method: "POST" });
      const t = await r.text();
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
      setMsg(`✅ 赔率拉取成功：${t}`);
    } catch (e) {
      setMsg(`❌ 赔率拉取失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function snapshotPredictions() {
    setLoading(true);
    setMsg("");
    try {
      const r = await workbenchFetch("/api/predictions/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: snapshotDate }),
      });
      const t = await r.text();
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
      setMsg(`✅ 预测快照已写入：${t}`);
    } catch (e) {
      setMsg(`❌ 预测快照失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function runBacktest() {
    setLoading(true);
    setMsg("");
    setBtResult(null);
    try {
      const url = `/api/backtest?date_from=${encodeURIComponent(btFrom)}&date_to=${encodeURIComponent(btTo)}`;
      const r = await workbenchFetch(url, { cache: "no-store" });
      const j = (await r.json()) as BacktestResponse;
      if (r.status === 401) {
        setNeedAuth(true);
        throw new Error("需要工作台管理员身份认证（请先在本页完成登录）");
      }
      if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
      setBtResult(j);
      setMsg("✅ 回测完成（结果已显示在下方）");
    } catch (e) {
      setMsg(`❌ 回测失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="系统"
        title="环境、导入与回测"
        description="先确认环境与数据库健康，再执行导入、赔率拉取、赛前快照与赛后回测。"
        actions={
          <>
            <PrimaryLink href="/fixtures">查看赛程</PrimaryLink>
            <SecondaryLink href="/predictions">查看预测</SecondaryLink>
          </>
        }
      />

      {needAuth ? (
        <WorkbenchLoginInline
          title="管理员登录（用于系统操作）"
          onSuccess={() => {
            setNeedAuth(false);
          }}
        />
      ) : null}

      <StatStrip
        items={[
          {
            label: "环境就绪",
            value: status ? `${envReadyCount}/5` : "…",
            hint: "除 Supabase 外均视为可选能力",
            tone: status && envReadyCount >= 5 ? "success" : undefined,
          },
          {
            label: "数据库状态",
            value: status?.supabase.ok == null ? "待检查" : status.supabase.ok ? "正常" : "异常",
            hint: "基于 fixtures 表连通性",
            tone: status?.supabase.ok == null ? undefined : status.supabase.ok ? "success" : "danger",
          },
          {
            label: "fixtures 记录",
            value: status?.supabase.fixturesCount != null ? String(status.supabase.fixturesCount) : "—",
            hint: "当前库内比赛数",
          },
          {
            label: "赔率能力",
            value: status?.env.hasApiFootballKey ? "已启用" : "未启用",
            hint: "自动拉取赔率",
            tone: status?.env.hasApiFootballKey ? "success" : undefined,
          },
        ]}
      />

      {msg ? (
        <section className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-700">
          <pre className="whitespace-pre-wrap font-sans">{msg}</pre>
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SurfaceCard
          title="环境与连接"
          action={
            <ActionButton tone="secondary" onClick={refresh} disabled={loading}>
              刷新状态
            </ActionButton>
          }
        >
          <div className="divide-y divide-zinc-100">
            {[
              { label: "SUPABASE_URL", ok: status?.env.hasSupabaseUrl, missingTone: "danger" as const },
              { label: "SUPABASE_SERVICE_ROLE_KEY", ok: status?.env.hasSupabaseServiceRole, missingTone: "danger" as const },
              { label: "FOOTBALL_DATA_API_KEY", ok: status?.env.hasFootballDataKey, missingTone: "warning" as const },
              { label: "OPENROUTER_API_KEY", ok: status?.env.hasOpenRouterKey, missingTone: "warning" as const },
              { label: "API_FOOTBALL_KEY", ok: status?.env.hasApiFootballKey, missingTone: "warning" as const },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                <span className="font-mono text-xs text-zinc-600">{item.label}</span>
                <StatusBadge tone={item.ok ? "success" : item.missingTone}>{item.ok ? "已配置" : "未配置"}</StatusBadge>
              </div>
            ))}
          </div>
          <div className="mt-3 border-t border-zinc-100 pt-3 text-xs text-zinc-500">
            OpenRouter 模型：<span className="text-zinc-900">{status?.env.openRouterModel || "未显式设置"}</span>
          </div>
          {status?.supabase.ok === false ? (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">
              Supabase 连接失败：{status.supabase.error}
            </div>
          ) : null}
          {status?.supabase.ok === true ? (
            <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-xs text-emerald-800">
              Supabase 连接正常，fixtures 记录数：{status.supabase.fixturesCount ?? "-"}
            </div>
          ) : null}
        </SurfaceCard>

        <SurfaceCard title="操作顺序">
          <ol className="divide-y divide-zinc-100 text-sm text-zinc-600">
            {[
              "刷新状态，确认数据库与环境变量正常。",
              "导入比赛数据，再按需拉取赔率。",
              "赛前保存预测快照，避免回测时信息穿越。",
              "赛后运行回测，关注样本量、准确率、Logloss 与 Brier。",
            ].map((text, index) => (
              <li key={text} className="flex gap-3 py-2.5 first:pt-0 last:pb-0">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs text-zinc-600">
                  {index + 1}
                </span>
                <span className="leading-5">{text}</span>
              </li>
            ))}
          </ol>
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SurfaceCard title="导入比赛数据" description="导入成功后比赛页与预测页同步可用。">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>开始日期</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>结束日期</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
          </div>
          {!coreEnvOk ? (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">
              需要先配置 SUPABASE_URL 与 SUPABASE_SERVICE_ROLE_KEY，否则无法写入数据库。
            </div>
          ) : !status?.env.hasFootballDataKey ? (
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
              未配置 FOOTBALL_DATA_API_KEY，football-data 导入不可用；体彩赛程 + 本地分析产物主流程不受影响。
            </div>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <ActionButton onClick={ingest} disabled={loading || !canIngestFootballData}>
              {loading ? "导入中…" : "开始导入"}
            </ActionButton>
          </div>
        </SurfaceCard>

        <SurfaceCard title="拉取赔率" description="赔率写入后，预测页的价值判断更完整。">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>日期</span>
              <input
                type="date"
                value={oddsDate}
                onChange={(e) => setOddsDate(e.target.value)}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <ActionButton onClick={ingestOdds} disabled={loading || !status?.env?.hasApiFootballKey}>
              {loading ? "拉取中…" : "拉取赔率"}
            </ActionButton>
          </div>
          {!status?.env?.hasApiFootballKey ? (
            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
              未配置 API_FOOTBALL_KEY，赔率拉取不可用。
            </div>
          ) : null}
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SurfaceCard title="保存预测快照" description="回测应基于赛前快照，而不是事后重新生成的预测。">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>日期</span>
              <input
                type="date"
                value={snapshotDate}
                onChange={(e) => setSnapshotDate(e.target.value)}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <ActionButton onClick={snapshotPredictions} disabled={loading}>
              {loading ? "保存中…" : "保存快照"}
            </ActionButton>
          </div>
        </SurfaceCard>

        <SurfaceCard title="运行回测" description="赛后核对样本量与概率质量。">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>开始日期</span>
              <input
                type="date"
                value={btFrom}
                onChange={(e) => setBtFrom(e.target.value)}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>结束日期</span>
              <input
                type="date"
                value={btTo}
                onChange={(e) => setBtTo(e.target.value)}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <ActionButton onClick={runBacktest} disabled={loading}>
              {loading ? "回测中…" : "开始回测"}
            </ActionButton>
          </div>
          {btResult?.summary ? (
            <div className="mt-3">
              <StatStrip
                items={[
                  { label: "样本数 n", value: String(btResult.summary.n) },
                  {
                    label: "Accuracy",
                    value: btResult.summary.accuracy != null ? `${(btResult.summary.accuracy * 100).toFixed(1)}%` : "-",
                  },
                  { label: "Logloss", value: btResult.summary.logloss != null ? btResult.summary.logloss.toFixed(4) : "-" },
                  { label: "Brier", value: btResult.summary.brier != null ? btResult.summary.brier.toFixed(4) : "-" },
                ]}
              />
              <div className="mt-2 text-xs text-zinc-500">n = 0 通常表示还没有赛前快照，或比赛结果未更新为 FINISHED。</div>
            </div>
          ) : null}
        </SurfaceCard>
      </div>
    </div>
  );
}
