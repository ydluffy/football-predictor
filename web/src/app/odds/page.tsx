"use client";

import { useEffect, useMemo, useState } from "react";
import { ActionButton, EmptyState, PageIntro, PrimaryLink, SecondaryLink, StatStrip, StatusBadge, SurfaceCard } from "@/components/Workbench";
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
    <span className="tabular-nums">
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

const TH = "whitespace-nowrap px-3 py-2 text-xs font-medium";
const TD = "px-3 py-2.5 text-xs align-top";

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
    <div className="grid gap-5">
      <PageIntro
        eyebrow={date}
        title="赔率"
        description="上半屏看覆盖（有直接赔率 / 只有预测快照 / 缺失），下半屏看价值（隐含概率、返还率、凯利指数）。"
        actions={
          <>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-zinc-400"
            />
            <PrimaryLink href={`/fixtures?date=${date}`}>回到比赛</PrimaryLink>
            <SecondaryLink href="/predictions">查看预测</SecondaryLink>
          </>
        }
      />

      <StatStrip
        columns={6}
        items={[
          { label: "当日比赛", value: busy ? "…" : String(rows.length) },
          { label: "直接赔率覆盖", value: busy ? "…" : directCoverage, hint: `已写入 ${directCount} 场` },
          { label: "总覆盖率", value: busy ? "…" : totalCoverage, hint: `缺失 ${missingCount} 场` },
          {
            label: "平均返还率",
            value: busy ? "…" : avgPayoutRate != null ? `${(avgPayoutRate * 100).toFixed(1)}%` : "—",
          },
          {
            label: "价值方向",
            value: busy ? "…" : String(valueSideCount),
            hint: "凯利 > 1",
            tone: valueSideCount > 0 ? "success" : "neutral",
          },
          {
            label: "双链路齐全",
            value: busy ? "…" : String(fullyCoveredCount),
            hint: `快照 ${snapshotCount} 场`,
          },
        ]}
      />

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">赔率状态加载失败：{error}</div>
      ) : null}

      <SurfaceCard title="覆盖与缺口">
        <div className="grid gap-4 lg:grid-cols-2 lg:gap-0 lg:divide-x lg:divide-zinc-100">
          <div className="lg:pr-4">
            <div className="text-xs text-zinc-500">来源分组</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
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
            <div className="mt-2 text-xs text-zinc-400">直接赔率最新采集：{formatAt(latestDirectCollectedAt)}</div>
          </div>
          <div className="lg:pl-4">
            <div className="text-xs text-zinc-500">缺失分组</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
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
            <div className="mt-2 text-xs text-zinc-400">预测快照最新生成：{formatAt(latestSnapshotGeneratedAt)}</div>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard
        title="赔率明细"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-zinc-400">
              {showOnlyMissing ? `缺失 ${filteredRows.length} 场` : `${filteredRows.length} 场`}
            </span>
            <ActionButton tone="secondary" onClick={() => setShowOnlyMissing((v) => !v)}>
              {showOnlyMissing ? "显示全部" : "只看缺失"}
            </ActionButton>
          </div>
        }
      >
        {filteredRows.length === 0 ? (
          <EmptyState text={showOnlyMissing ? "当前没有完全缺失赔率的场次。" : "当前日期还没有赔率状态记录。"} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1120px] text-sm">
              <thead className="border-b border-zinc-200 bg-zinc-50">
                <tr className="text-zinc-500">
                  <th className={`${TH} text-left`}>比赛</th>
                  <th className={`${TH} text-left`}>市场赔率 / 隐含概率</th>
                  <th className={`${TH} text-right`}>返还率</th>
                  <th className={`${TH} text-left`}>模型概率</th>
                  <th className={`${TH} text-left`}>凯利指数</th>
                  <th className={`${TH} text-left`}>价值方向</th>
                  <th className={`${TH} text-left`}>快照与状态</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {filteredRows.map((row) => {
                  const competition = row.competition_name_zh || competitionNameZh(undefined, row.competition_name);
                  const kickoff = row.kickoff_time_zh || formatLocalTimeFromUtc(row.utc_date, "Asia/Shanghai");
                  return (
                    <tr key={row.fixture_id}>
                      <td className={TD}>
                        <div className="font-medium text-zinc-900">
                          {row.home_team_name_zh || teamNameZh(row.home_team_name)} vs {row.away_team_name_zh || teamNameZh(row.away_team_name)}
                        </div>
                        <div className="mt-0.5 flex flex-wrap gap-x-2 text-zinc-400">
                          <span className="tabular-nums">{row.sporttery_match_number || row.fixture_id}</span>
                          <span>{competition || "—"}</span>
                          <span className="tabular-nums">{kickoff || "—"}</span>
                        </div>
                      </td>
                      <td className={TD}>
                        <div className="tabular-nums text-zinc-900">{oddsTripleText(row.odds_home, row.odds_draw, row.odds_away)}</div>
                        <div className="mt-0.5 tabular-nums text-zinc-400">
                          隐含 {probTripleText(row.implied_home, row.implied_draw, row.implied_away)}
                        </div>
                        <div className="mt-0.5 text-zinc-400">
                          {row.bookmaker || "—"} · {formatAt(row.collected_at)}
                        </div>
                      </td>
                      <td className={`${TD} text-right tabular-nums text-zinc-700`}>
                        {row.payout_rate != null ? `${(row.payout_rate * 100).toFixed(1)}%` : "—"}
                      </td>
                      <td className={`${TD} tabular-nums text-zinc-700`}>
                        {probTripleText(row.model_p_home, row.model_p_draw, row.model_p_away)}
                      </td>
                      <td className={`${TD} text-zinc-700`}>{kellyTriple(row) || "—"}</td>
                      <td className={TD}>
                        {row.value_side ? (
                          <StatusBadge tone="success">
                            {row.value_side} +{Math.round((row.value_edge || 0) * 100)}%
                          </StatusBadge>
                        ) : (
                          <span className="text-zinc-400">—</span>
                        )}
                      </td>
                      <td className={TD}>
                        <div className="tabular-nums text-zinc-700">
                          {oddsTripleText(row.prediction_odds_home, row.prediction_odds_draw, row.prediction_odds_away)}
                        </div>
                        <div className="mt-0.5 text-zinc-400">
                          {row.prediction_model_version || "—"} · {row.prediction_source || row.prediction_bookmaker || "无来源"} ·{" "}
                          {formatAt(row.prediction_generated_at)}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1.5">
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
