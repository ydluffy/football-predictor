"use client";

import { useEffect, useMemo, useState } from "react";
import { ActionButton, EmptyState, MetricCard, PageIntro, PrimaryLink, SecondaryLink, StatusBadge, SurfaceCard } from "@/components/Workbench";
import { getOddsStatus, type OddsStatusItem } from "@/lib/api";
import { getShanghaiToday } from "@/lib/time";
import { competitionNameZh, formatLocalTimeFromUtc, teamNameZh } from "@/lib/zh";

function oddsTripleText(home?: number | null, draw?: number | null, away?: number | null) {
  if (home == null && draw == null && away == null) return "—";
  return `${home ?? "-"} / ${draw ?? "-"} / ${away ?? "-"}`;
}

function probTripleText(home?: number | null, draw?: number | null, away?: number | null) {
  if (home == null && draw == null && away == null) return "—";
  const pct = (value?: number | null) => (value == null ? "-" : `${Math.round(value * 100)}%`);
  return `${pct(home)} / ${pct(draw)} / ${pct(away)}`;
}

function kellyTriple(row: OddsStatusItem) {
  if (row.kelly_home == null && row.kelly_draw == null && row.kelly_away == null) return null;
  const fmt = (value?: number | null) => (value == null ? "-" : value.toFixed(2));
  return (
    <span>
      <span className={row.kelly_home != null && row.kelly_home > 1 ? "font-semibold text-emerald-700" : ""}>{fmt(row.kelly_home)}</span>
      {" / "}
      <span className={row.kelly_draw != null && row.kelly_draw > 1 ? "font-semibold text-emerald-700" : ""}>{fmt(row.kelly_draw)}</span>
      {" / "}
      <span className={row.kelly_away != null && row.kelly_away > 1 ? "font-semibold text-emerald-700" : ""}>{fmt(row.kelly_away)}</span>
    </span>
  );
}

function formatAt(value?: string | null) {
  if (!value) return "—";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(dt);
}

export default function OddsPage() {
  const [date, setDate] = useState(getShanghaiToday());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<OddsStatusItem[]>([]);
  const [showOnlyMissing, setShowOnlyMissing] = useState(false);
  const [sourceSummary, setSourceSummary] = useState<Array<{ bookmaker: string; count: number }>>([]);
  const [missingSummary, setMissingSummary] = useState<Array<{ reason: string; count: number }>>([]);
  const [latestDirectCollectedAt, setLatestDirectCollectedAt] = useState<string | null>(null);
  const [latestSnapshotGeneratedAt, setLatestSnapshotGeneratedAt] = useState<string | null>(null);
  const [avgPayoutRate, setAvgPayoutRate] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setBusy(true);
      setError(null);
      try {
        const data = await getOddsStatus(date);
        if (!mounted) return;
        setRows(data.rows || []);
        setSourceSummary(data.source_summary || []);
        setMissingSummary(data.missing_summary || []);
        setLatestDirectCollectedAt(data.latest_direct_collected_at || null);
        setLatestSnapshotGeneratedAt(data.latest_snapshot_generated_at || null);
        setAvgPayoutRate(data.avg_payout_rate ?? null);
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : String(e));
        setRows([]);
        setSourceSummary([]);
        setMissingSummary([]);
        setLatestDirectCollectedAt(null);
        setLatestSnapshotGeneratedAt(null);
        setAvgPayoutRate(null);
      } finally {
        if (mounted) setBusy(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [date]);

  const directCount = useMemo(() => rows.filter((item) => item.has_direct_odds).length, [rows]);
  const snapshotCount = useMemo(() => rows.filter((item) => item.has_prediction_snapshot_odds).length, [rows]);
  const missingCount = useMemo(
    () => rows.filter((item) => !item.has_direct_odds && !item.has_prediction_snapshot_odds).length,
    [rows],
  );
  const fullyCoveredCount = useMemo(() => rows.filter((item) => item.status_mode === "both").length, [rows]);
  const valueSideCount = useMemo(() => rows.filter((item) => item.value_side).length, [rows]);
  const directCoverage = useMemo(() => (rows.length > 0 ? `${Math.round((directCount / rows.length) * 100)}%` : "0%"), [directCount, rows.length]);
  const totalCoverage = useMemo(
    () => (rows.length > 0 ? `${Math.round(((rows.length - missingCount) / rows.length) * 100)}%` : "0%"),
    [missingCount, rows.length],
  );
  const filteredRows = useMemo(
    () => (showOnlyMissing ? rows.filter((item) => !item.has_direct_odds && !item.has_prediction_snapshot_odds) : rows),
    [rows, showOnlyMissing],
  );

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="赔率获取监控"
        title="赔率拿到了没有，值不值得下"
        description="上半屏看覆盖：哪些场次有直接赔率、哪些只有预测快照、哪些缺失。下半屏看价值：隐含概率、返还率和模型凯利指数全部由现有数据直接计算，不需要新增采集。"
        actions={
          <>
            <PrimaryLink href={`/fixtures?date=${date}`}>回到比赛</PrimaryLink>
            <SecondaryLink href="/predictions">查看预测</SecondaryLink>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="当日比赛" value={busy ? "…" : String(rows.length)} hint="当前销售日比赛总数" />
        <MetricCard label="直接赔率覆盖" value={busy ? "…" : directCoverage} hint={`已写入 ${directCount} 场`} />
        <MetricCard label="总覆盖率" value={busy ? "…" : totalCoverage} hint={`缺失 ${missingCount} 场`} />
        <MetricCard
          label="平均返还率"
          value={busy ? "…" : avgPayoutRate != null ? `${(avgPayoutRate * 100).toFixed(1)}%` : "—"}
          hint="按可计算场次的三向赔率均值"
        />
        <MetricCard label="价值方向" value={busy ? "…" : String(valueSideCount)} hint="模型凯利指数大于 1 的场次" />
        <MetricCard
          label="双链路齐全"
          value={busy ? "…" : String(fullyCoveredCount)}
          hint={`快照赔率 ${snapshotCount} 场，最新 ${formatAt(latestDirectCollectedAt)}`}
        />
      </section>

      {error ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">赔率状态加载失败：{error}</section>
      ) : null}

      <SurfaceCard
        title="覆盖与缺口"
        description="先看今天赔率数据主要来自哪些机构，再看缺失集中在哪一类。"
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-zinc-200 bg-white p-4">
            <div className="text-sm font-semibold text-zinc-950">来源分组</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {sourceSummary.length === 0 ? (
                <StatusBadge tone="neutral">暂无直接赔率来源</StatusBadge>
              ) : (
                sourceSummary.map((item) => (
                  <StatusBadge key={item.bookmaker} tone="success">
                    {item.bookmaker} · {item.count}
                  </StatusBadge>
                ))
              )}
            </div>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-white p-4">
            <div className="text-sm font-semibold text-zinc-950">缺失分组</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {missingSummary.length === 0 ? (
                <StatusBadge tone="success">当前没有明显缺口</StatusBadge>
              ) : (
                missingSummary.map((item) => (
                  <StatusBadge key={item.reason} tone="warning">
                    {item.reason} · {item.count}
                  </StatusBadge>
                ))
              )}
            </div>
            <div className="mt-3 text-xs text-zinc-500">预测快照最新生成时间：{formatAt(latestSnapshotGeneratedAt)}</div>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard
        title="赔率获取与价值明细"
        description="隐含概率 = 1/赔率（含抽水）；返还率 = 1/Σ(1/赔率)；凯利指数 = 模型概率 × 赔率，大于 1 标绿表示模型认为该方向有正期望。指标优先用直接赔率计算，缺失时退回预测快照赔率。"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
            />
            <ActionButton tone="secondary" onClick={() => setShowOnlyMissing((v) => !v)}>
              {showOnlyMissing ? "显示全部" : "只看缺失"}
            </ActionButton>
          </div>
        }
      >
        {filteredRows.length === 0 ? (
          <EmptyState text={showOnlyMissing ? "当前没有完全缺失赔率的场次。" : "当前日期还没有赔率状态记录。"} />
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-zinc-200">
            <table className="min-w-[1460px] w-full border-separate border-spacing-0 text-sm">
              <thead className="bg-zinc-50 text-xs text-zinc-500">
                <tr>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">编号</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">赛事</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">对阵</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">开赛时间</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">赔率（主/平/客）</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">隐含概率</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">返还率</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">模型概率</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">凯利指数</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">价值方向</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">快照赔率</th>
                  <th className="border-b border-zinc-200 px-3 py-3 text-left">状态</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const competition = row.competition_name_zh || competitionNameZh(undefined, row.competition_name);
                  const kickoff = row.kickoff_time_zh || formatLocalTimeFromUtc(row.utc_date, "Asia/Shanghai");
                  return (
                    <tr key={row.fixture_id} className="bg-white">
                      <td className="border-b border-zinc-200 px-3 py-3 align-top font-medium text-zinc-900">
                        {row.sporttery_match_number || row.fixture_id}
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">{competition || "—"}</td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top">
                        <div className="font-medium text-zinc-950">
                          {row.home_team_name_zh || teamNameZh(row.home_team_name)} vs {row.away_team_name_zh || teamNameZh(row.away_team_name)}
                        </div>
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">{kickoff || "—"}</td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">
                        {oddsTripleText(row.odds_home, row.odds_draw, row.odds_away)}
                        <div className="mt-1 text-xs text-zinc-500">
                          {row.bookmaker || "—"} · 采集 {formatAt(row.collected_at)}
                        </div>
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">
                        {probTripleText(row.implied_home, row.implied_draw, row.implied_away)}
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">
                        {row.payout_rate != null ? `${(row.payout_rate * 100).toFixed(1)}%` : "—"}
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">
                        {probTripleText(row.model_p_home, row.model_p_draw, row.model_p_away)}
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">{kellyTriple(row) || "—"}</td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top">
                        {row.value_side ? (
                          <StatusBadge tone="success">
                            {row.value_side} +{Math.round((row.value_edge || 0) * 100)}%
                          </StatusBadge>
                        ) : (
                          <span className="text-sm text-zinc-400">—</span>
                        )}
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">
                        {oddsTripleText(row.prediction_odds_home, row.prediction_odds_draw, row.prediction_odds_away)}
                        <div className="mt-1 text-xs text-zinc-500">
                          {row.prediction_model_version || "—"} · {row.prediction_source || row.prediction_bookmaker || "无来源"} ·{" "}
                          {formatAt(row.prediction_generated_at)}
                        </div>
                      </td>
                      <td className="border-b border-zinc-200 px-3 py-3 align-top">
                        <div className="flex flex-wrap gap-2">
                          <StatusBadge tone={row.has_direct_odds ? "success" : "neutral"}>
                            {row.has_direct_odds ? "直接赔率" : "无直接赔率"}
                          </StatusBadge>
                          <StatusBadge tone={row.has_prediction_snapshot_odds ? "warning" : "neutral"}>
                            {row.has_prediction_snapshot_odds ? "快照赔率" : "无快照"}
                          </StatusBadge>
                          {row.missing_reason ? <StatusBadge tone="danger">{row.missing_reason}</StatusBadge> : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SurfaceCard>
    </div>
  );
}
