"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ActionButton,
  MetricCard,
  PageIntro,
  PrimaryLink,
  SecondaryLink,
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
        eyebrow="系统工作页"
        title="把环境、导入、赔率、快照和回测收在一个地方"
        description="这页不再只是部署说明，而是完整的运行控制面板。先看环境和数据库健康，再执行导入、赔率拉取、赛前快照和赛后回测。"
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

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="环境就绪"
          value={status ? `${envReadyCount}/5` : "…"}
          hint="提示：除 Supabase 外，其余 key 均为可选能力"
        />
        <MetricCard
          label="数据库状态"
          value={status?.supabase.ok == null ? "待检查" : status.supabase.ok ? "正常" : "异常"}
          hint="基于 `fixtures` 表连通性检测"
        />
        <MetricCard
          label="fixtures 记录"
          value={status?.supabase.fixturesCount != null ? String(status.supabase.fixturesCount) : "—"}
          hint="当前 Supabase 中的比赛记录数"
        />
        <MetricCard
          label="赔率能力"
          value={status?.env.hasApiFootballKey ? "已启用" : "未启用"}
          hint="决定是否可自动拉取赔率数据"
        />
      </section>

      {msg ? (
        <section className="rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-700 shadow-sm">
          <pre className="whitespace-pre-wrap font-sans">{msg}</pre>
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SurfaceCard
          title="环境与连接"
          description="先确认运行环境是否齐，再执行下面的导入与回测动作。"
          action={
            <ActionButton tone="secondary" onClick={refresh} disabled={loading}>
              刷新状态
            </ActionButton>
          }
        >
          <div className="grid gap-3">
            <div className="flex items-center justify-between rounded-xl border border-zinc-200 px-4 py-3">
              <span className="text-sm text-zinc-600">SUPABASE_URL</span>
              <StatusBadge tone={status?.env.hasSupabaseUrl ? "success" : "danger"}>
                {status?.env.hasSupabaseUrl ? "已配置" : "缺失"}
              </StatusBadge>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-zinc-200 px-4 py-3">
              <span className="text-sm text-zinc-600">SUPABASE_SERVICE_ROLE_KEY</span>
              <StatusBadge tone={status?.env.hasSupabaseServiceRole ? "success" : "danger"}>
                {status?.env.hasSupabaseServiceRole ? "已配置" : "缺失"}
              </StatusBadge>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-zinc-200 px-4 py-3">
              <span className="text-sm text-zinc-600">FOOTBALL_DATA_API_KEY</span>
              <StatusBadge tone={status?.env.hasFootballDataKey ? "success" : "warning"}>
                {status?.env.hasFootballDataKey ? "已配置" : "未配置"}
              </StatusBadge>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-zinc-200 px-4 py-3">
              <span className="text-sm text-zinc-600">OPENROUTER_API_KEY</span>
              <StatusBadge tone={status?.env.hasOpenRouterKey ? "success" : "warning"}>
                {status?.env.hasOpenRouterKey ? "已配置" : "未配置"}
              </StatusBadge>
            </div>
            <div className="flex items-center justify-between rounded-xl border border-zinc-200 px-4 py-3">
              <span className="text-sm text-zinc-600">API_FOOTBALL_KEY</span>
              <StatusBadge tone={status?.env.hasApiFootballKey ? "success" : "warning"}>
                {status?.env.hasApiFootballKey ? "已配置" : "未配置"}
              </StatusBadge>
            </div>
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600">
              OpenRouter 模型：<span className="font-medium text-zinc-900">{status?.env.openRouterModel || "未显式设置"}</span>
            </div>
            {status?.supabase.ok === false ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                Supabase 连接失败：{status.supabase.error}
              </div>
            ) : null}
            {status?.supabase.ok === true ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                Supabase 连接正常，当前 `fixtures` 表记录数：{status.supabase.fixturesCount ?? "-"}
              </div>
            ) : null}
          </div>
        </SurfaceCard>

        <SurfaceCard
          title="操作提示"
          description="建议按这个顺序操作，能尽量减少数据不完整导致的误判。"
        >
          <div className="grid gap-3 text-sm">
            <div className="rounded-xl border border-zinc-200 px-4 py-3">1. 先刷新状态，确认数据库和环境变量都正常。</div>
            <div className="rounded-xl border border-zinc-200 px-4 py-3">2. 导入比赛数据，再按需拉取赔率。</div>
            <div className="rounded-xl border border-zinc-200 px-4 py-3">3. 赛前先保存预测快照，避免回测时出现信息穿越。</div>
            <div className="rounded-xl border border-zinc-200 px-4 py-3">4. 赛后再运行回测，关注样本量、准确率、Logloss 和 Brier。</div>
          </div>
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SurfaceCard title="导入比赛数据" description="导入成功后，比赛页和预测页都会同步可用。">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>date_from</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>date_to</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
          </div>
          {!coreEnvOk ? (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              需要先配置 `SUPABASE_URL` 与 `SUPABASE_SERVICE_ROLE_KEY`，否则无法写入数据库。
            </div>
          ) : !status?.env.hasFootballDataKey ? (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              当前没有 `FOOTBALL_DATA_API_KEY`，因此“football-data 导入”不可用。
              <span className="ml-1">
                不过你现在的主流程（体彩赛程 + 本地分析产物）仍然可以正常使用。
              </span>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <ActionButton onClick={ingest} disabled={loading || !canIngestFootballData}>
              {loading ? "导入中…" : "开始导入"}
            </ActionButton>
          </div>
        </SurfaceCard>

        <SurfaceCard title="拉取赔率" description="赔率写入后，预测页的价值投注说明会更完整。">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>date</span>
              <input
                type="date"
                value={oddsDate}
                onChange={(e) => setOddsDate(e.target.value)}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <ActionButton onClick={ingestOdds} disabled={loading || !status?.env?.hasApiFootballKey}>
              {loading ? "拉取中…" : "拉取赔率"}
            </ActionButton>
          </div>
          {!status?.env?.hasApiFootballKey ? (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              当前没有 `API_FOOTBALL_KEY`，赔率拉取能力不可用。
            </div>
          ) : null}
        </SurfaceCard>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SurfaceCard title="保存预测快照" description="赛前先保存，给后续回测提供真实的赛前视角。">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>date</span>
              <input
                type="date"
                value={snapshotDate}
                onChange={(e) => setSnapshotDate(e.target.value)}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <ActionButton onClick={snapshotPredictions} disabled={loading}>
              {loading ? "保存中…" : "保存快照"}
            </ActionButton>
          </div>
          <div className="mt-4 text-sm text-zinc-500">
            回测应该基于赛前快照，而不是事后重新生成的预测结果。
          </div>
        </SurfaceCard>

        <SurfaceCard title="运行回测" description="赛后核对样本量和概率质量，重点看 Logloss 与 Brier。">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>date_from</span>
              <input
                type="date"
                value={btFrom}
                onChange={(e) => setBtFrom(e.target.value)}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
            <label className="grid gap-2 text-sm text-zinc-600">
              <span>date_to</span>
              <input
                type="date"
                value={btTo}
                onChange={(e) => setBtTo(e.target.value)}
                className="rounded-xl border border-zinc-200 bg-white px-3 py-2 outline-none focus:border-zinc-400"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <ActionButton onClick={runBacktest} disabled={loading}>
              {loading ? "回测中…" : "开始回测"}
            </ActionButton>
          </div>
          {btResult?.summary ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700">
                样本数 n
                <div className="mt-1 text-xl font-semibold text-zinc-950">{btResult.summary.n}</div>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700">
                Accuracy
                <div className="mt-1 text-xl font-semibold text-zinc-950">
                  {btResult.summary.accuracy != null ? `${(btResult.summary.accuracy * 100).toFixed(1)}%` : "-"}
                </div>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700">
                Logloss
                <div className="mt-1 text-xl font-semibold text-zinc-950">
                  {btResult.summary.logloss != null ? btResult.summary.logloss.toFixed(4) : "-"}
                </div>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700">
                Brier
                <div className="mt-1 text-xl font-semibold text-zinc-950">
                  {btResult.summary.brier != null ? btResult.summary.brier.toFixed(4) : "-"}
                </div>
              </div>
            </div>
          ) : null}
          <div className="mt-4 text-sm text-zinc-500">
            如果 `n = 0`，通常说明还没有赛前快照，或者比赛结果尚未更新为 `FINISHED`。
          </div>
        </SurfaceCard>
      </div>
    </div>
  );
}
