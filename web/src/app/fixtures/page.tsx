"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import type { AnalysisRunLedgerItem, Fixture, FixtureLedgerRegistry, FixtureLedgerRow, FixtureMarketIntel, OddsChangeInfo, Prediction } from "@/lib/api";
import { getFixtureLedger, getFixtures, getMarketIntel, getPredictionsByDate, ingestFootballData } from "@/lib/api";
import { MatchDetailCard } from "@/components/MatchDetailCard";
import {
  ActionButton,
  Chip,
  EmptyState,
  PageIntro,
  StatStrip,
  StatusBadge,
  SurfaceCard,
} from "@/components/Workbench";
import { getShanghaiToday } from "@/lib/time";
import { competitionNameZh, formatLocalTimeFromUtc, teamNameZh } from "@/lib/zh";
import { evaluateSportteryHandicap } from "@/lib/handicap";

const SIGNAL_FILTERS = [
  { id: "movement", label: "有盘口变化" },
  { id: "upgrade_divergence", label: "升盘背离" },
  { id: "downgrade", label: "退盘" },
  { id: "aligned_only", label: "时间已对齐" },
  { id: "large_gap", label: "内外盘差较大" },
] as const;

type SignalFilterId = (typeof SIGNAL_FILTERS)[number]["id"];

function getWeekLabel(date: string) {
  const day = new Date(`${date}T12:00:00+08:00`).getDay();
  return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][day] || "周?";
}

function formatUpdatedAt(value?: string | null) {
  if (!value) return "—";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(dt);
}

function getSportteryCode(fixtureId: number, date: string, index: number) {
  const text = String(fixtureId);
  const matched = text.match(/^(\d{4})(\d{2})(\d{2})(\d{3})$/);
  if (matched && `${matched[1]}-${matched[2]}-${matched[3]}` === date) {
    return `${getWeekLabel(date)}${matched[4]}`;
  }
  return `${getWeekLabel(date)}${String(index + 1).padStart(3, "0")}`;
}

function getLeagueBadgeClass(name?: string | null) {
  const text = name || "";
  if (text.includes("日职")) return "bg-lime-600 text-white";
  if (text.includes("日联赛杯")) return "bg-emerald-600 text-white";
  if (text.includes("意大利杯")) return "bg-indigo-500 text-white";
  if (text.includes("英冠")) return "bg-orange-600 text-white";
  if (text.includes("德国杯")) return "bg-rose-600 text-white";
  if (text.includes("巴甲") || text.includes("巴西杯")) return "bg-green-600 text-white";
  if (text.includes("瑞超")) return "bg-sky-600 text-white";
  if (text.includes("西甲")) return "bg-slate-700 text-white";
  if (text.includes("法甲")) return "bg-blue-600 text-white";
  return "bg-zinc-500 text-white";
}

function getRiskHint(pred?: Prediction | null, intel?: FixtureMarketIntel | null) {
  if (pred?.risk_note) return pred.risk_note;
  if (!intel) return "暂无市场信号";
  if (intel.movement?.line_upgrade_without_price_support) return "升盘背离，注意热度风险";
  if (intel.movement?.line_downgrade) return "存在退盘，谨防方向反复";
  if (Math.abs(intel.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5) {
    const diff = intel.alignment?.sporttery_minus_outer_handicap_median ?? 0;
    return `内外盘差 ${diff > 0 ? "+" : ""}${diff.toFixed(2)}`;
  }
  if (intel.alignment?.time_aligned) return "无显著风险（已对齐）";
  if (intel.movement) return "无显著风险（有盘口变化）";
  return "无显著风险";
}

function getGoalsScoreView(pred?: Prediction | null) {
  if (!pred) return "—";
  const goals = pred.total_goals_suggestion?.trim();
  const scores = pred.correct_score_suggestion?.trim();
  if (goals && scores) return `${goals}；${scores}`;
  if (scores) return scores;
  if (goals) return goals;

  const topScores = pred.scorelines_top?.slice(0, 2).map((s) => `${s.home_goals}:${s.away_goals}`).join("、");
  if (topScores) return `比分参考 ${topScores}`;
  return "—";
}

function getOutcomeLabel(pred?: Prediction | null) {
  if (!pred) return "—";
  const top = [
    { label: "主胜", value: pred.p_home },
    { label: "平", value: pred.p_draw },
    { label: "客胜", value: pred.p_away },
  ].sort((a, b) => b.value - a.value)[0];
  return `${top.label} ${Math.round(top.value * 100)}%`;
}

// 官方 SPF 赔率变化展示：主赔率初→终 + 变标记，平客变化作次行
function renderOddsChange(change?: OddsChangeInfo | null) {
  if (!change) return <span className="text-sm text-zinc-300">—</span>;
  const [beforeHome, beforeDraw, beforeAway] = change.before;
  const [afterHome, afterDraw, afterAway] = change.after;
  if (beforeHome == null && afterHome == null) return <span className="text-sm text-zinc-300">—</span>;
  const fmt = (value: number | null) => (value == null ? "-" : value.toFixed(2));
  const homeDrop = beforeHome != null && afterHome != null && afterHome < beforeHome;
  const homeRise = beforeHome != null && afterHome != null && afterHome > beforeHome;
  return (
    <div>
      <div className="flex items-center gap-1.5 text-sm tabular-nums">
        <span
          className={
            change.changed
              ? homeDrop
                ? "font-semibold text-red-600"
                : homeRise
                  ? "font-semibold text-emerald-600"
                  : "font-semibold text-zinc-800"
              : "text-zinc-700"
          }
        >
          {fmt(beforeHome)}→{fmt(afterHome)}
        </span>
        {change.changed ? <Chip tone="warning">变</Chip> : null}
      </div>
      <div className="mt-0.5 text-xs tabular-nums text-zinc-400">
        平 {fmt(beforeDraw)}→{fmt(afterDraw)} · 客 {fmt(beforeAway)}→{fmt(afterAway)}
      </div>
    </div>
  );
}

function FixturesPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [date, setDate] = useState(getShanghaiToday());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [rows, setRows] = useState<Fixture[]>([]);
  const [marketIntel, setMarketIntel] = useState<Map<number, FixtureMarketIntel>>(new Map());
  const [predictions, setPredictions] = useState<Map<number, Prediction>>(new Map());
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRunLedgerItem[]>([]);
  const [registry, setRegistry] = useState<FixtureLedgerRegistry | null>(null);
  const [fixtureLedgerMap, setFixtureLedgerMap] = useState<Map<number, FixtureLedgerRow>>(new Map());
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [tableCollapsed, setTableCollapsed] = useState(false);

  const selectedFixtureId = useMemo(() => {
    const raw = searchParams.get("fixtureId");
    return raw ? Number(raw) : null;
  }, [searchParams]);
  const activeLeagues = useMemo(() => {
    const raw = searchParams.get("leagues");
    if (!raw) return [] as string[];
    return raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }, [searchParams]);
  const activeSignals = useMemo(() => {
    const raw = searchParams.get("signals");
    if (!raw) return [] as SignalFilterId[];
    return raw
      .split(",")
      .map((item) => item.trim())
      .filter((item): item is SignalFilterId => SIGNAL_FILTERS.some((filter) => filter.id === item));
  }, [searchParams]);

  const replaceParams = useCallback(
    (updater: (params: URLSearchParams) => void) => {
      const params = new URLSearchParams(searchParams.toString());
      updater(params);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const load = useCallback(async () => {
    setError(null);
    setPredictionError(null);
    setBusy(true);
    try {
      const r = await getFixtures(date);
      setRows(r.fixtures);
      setLastUpdatedAt(new Date().toISOString());
      try {
        const ledger = await getFixtureLedger(date);
        setAnalysisRuns(ledger.runs || []);
        setFixtureLedgerMap(new Map((ledger.fixtures || []).map((item) => [item.fixture_id, item])));
        setRegistry(ledger.registry || null);
      } catch {
        setAnalysisRuns([]);
        setFixtureLedgerMap(new Map());
        setRegistry(null);
      }
      try {
        const preds = await getPredictionsByDate(date);
        setPredictions(new Map((preds.predictions || []).map((item) => [item.fixture_id, item])));
      } catch (e) {
        setPredictions(new Map());
        setPredictionError(e instanceof Error ? e.message : String(e));
      }
      try {
        const intel = await getMarketIntel(r.fixtures);
        setMarketIntel(new Map(intel.items.map((item) => [item.fixture_id, item])));
      } catch {
        setMarketIntel(new Map());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMarketIntel(new Map());
      setPredictions(new Map());
      setAnalysisRuns([]);
      setFixtureLedgerMap(new Map());
      setRegistry(null);
    } finally {
      setBusy(false);
    }
  }, [date]);

  async function ingest() {
    setError(null);
    setBusy(true);
    try {
      await ingestFootballData(date, date);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const urlDate = searchParams.get("date");
    if (urlDate && urlDate !== date) {
      setDate(urlDate);
    }
  }, [date, searchParams]);

  useEffect(() => {
    load();
  }, [load]);

  const matchesWithScore = useMemo(
    () => rows.filter((r) => r.home_score != null && r.away_score != null).length,
    [rows],
  );
  const predictedCount = useMemo(() => rows.filter((row) => predictions.has(row.fixture_id)).length, [predictions, rows]);
  const competitionsCount = useMemo(
    () =>
      new Set(
        rows.map((r) => r.competition_code || r.competition_name_zh || r.competition_name).filter(Boolean),
      ).size,
    [rows],
  );
  const selectedFixture = useMemo(
    () => rows.find((row) => row.fixture_id === selectedFixtureId) || null,
    [rows, selectedFixtureId],
  );
  const leagueOptions = useMemo(
    () => [...new Set(rows.map((row) => row.competition_name_zh || competitionNameZh(row.competition_code, row.competition_name)).filter(Boolean))],
    [rows],
  );
  const filteredRows = useMemo(() => {
    const baseRows = rows.filter((row) => {
      const leagueName = row.competition_name_zh || competitionNameZh(row.competition_code, row.competition_name);
      if (activeLeagues.length > 0 && !activeLeagues.includes(leagueName)) return false;
      if (activeSignals.length === 0) return true;
      const intel = marketIntel.get(row.fixture_id);
      return activeSignals.every((signal) => {
        if (signal === "movement") return Boolean(intel?.movement);
        if (signal === "upgrade_divergence") return Boolean(intel?.movement?.line_upgrade_without_price_support);
        if (signal === "downgrade") return Boolean(intel?.movement?.line_downgrade);
        if (signal === "aligned_only") return Boolean(intel?.alignment?.time_aligned);
        if (signal === "large_gap") {
          return Math.abs(intel?.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5;
        }
        return true;
      });
    });

    return baseRows.sort((a, b) => {
      const left = a.utc_date || "";
      const right = b.utc_date || "";
      return left.localeCompare(right);
    });
  }, [activeLeagues, activeSignals, marketIntel, rows]);
  const filteredCount = filteredRows.length;
  const multiRunFixtureCount = useMemo(
    () => [...fixtureLedgerMap.values()].filter((item) => item.analysis_run_count >= 2).length,
    [fixtureLedgerMap],
  );
  const totalPlanCount = useMemo(
    () => analysisRuns.reduce((sum, item) => sum + item.real_plan_count, 0),
    [analysisRuns],
  );
  const totalStake = useMemo(
    () => analysisRuns.reduce((sum, item) => sum + item.total_stake, 0),
    [analysisRuns],
  );
  const signalCounts = useMemo(() => {
    const counts = new Map<SignalFilterId, number>();
    for (const filter of SIGNAL_FILTERS) counts.set(filter.id, 0);
    for (const row of rows) {
      const intel = marketIntel.get(row.fixture_id);
      if (intel?.movement) counts.set("movement", (counts.get("movement") || 0) + 1);
      if (intel?.movement?.line_upgrade_without_price_support) {
        counts.set("upgrade_divergence", (counts.get("upgrade_divergence") || 0) + 1);
      }
      if (intel?.movement?.line_downgrade) counts.set("downgrade", (counts.get("downgrade") || 0) + 1);
      if (intel?.alignment?.time_aligned) counts.set("aligned_only", (counts.get("aligned_only") || 0) + 1);
      if (Math.abs(intel?.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5) {
        counts.set("large_gap", (counts.get("large_gap") || 0) + 1);
      }
    }
    return counts;
  }, [marketIntel, rows]);
  const selectedPrediction = useMemo(
    () => (selectedFixture ? predictions.get(selectedFixture.fixture_id) || null : null),
    [predictions, selectedFixture],
  );
  const selectedFixtureSummary = useMemo(
    () => (selectedFixture ? fixtureLedgerMap.get(selectedFixture.fixture_id) || null : null),
    [fixtureLedgerMap, selectedFixture],
  );
  const selectedFixtureRuns = useMemo(() => {
    if (!selectedFixtureSummary || selectedFixtureSummary.analysis_run_count === 0) return [];
    const matchNumber =
      selectedFixtureSummary.sporttery_match_number ||
      getSportteryCode(
        selectedFixtureSummary.fixture_id,
        date,
        rows.findIndex((item) => item.fixture_id === selectedFixtureSummary.fixture_id),
      ).slice(-3);
    return analysisRuns.filter((run) => run.scope_match_numbers.includes(matchNumber));
  }, [analysisRuns, date, rows, selectedFixtureSummary]);

  const hasActiveFilter = activeLeagues.length > 0 || activeSignals.length > 0;

  function toggleLeague(league: string) {
    replaceParams((params) => {
      const current = new Set(activeLeagues);
      if (current.has(league)) current.delete(league);
      else current.add(league);
      if (current.size > 0) params.set("leagues", [...current].join(","));
      else params.delete("leagues");
    });
  }

  function toggleSignal(id: SignalFilterId) {
    replaceParams((params) => {
      const current = new Set(activeSignals);
      if (current.has(id)) current.delete(id);
      else current.add(id);
      if (current.size > 0) params.set("signals", [...current].join(","));
      else params.delete("signals");
    });
  }

  return (
    <div className="grid gap-4">
      <PageIntro
        eyebrow="竞彩"
        title="足球竞猜赛程"
        description={`比赛编号日期 ${date.replace(/-/g, "").slice(2)} · 数据更新 ${formatUpdatedAt(lastUpdatedAt)}`}
        actions={
          <>
            <input
              type="date"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                replaceParams((params) => {
                  params.set("date", e.target.value);
                  params.delete("fixtureId");
                });
              }}
              className="rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-400"
            />
            <ActionButton tone="secondary" onClick={load} disabled={busy}>
              刷新
            </ActionButton>
            <ActionButton onClick={ingest} disabled={busy}>
              {busy ? "处理中…" : "导入赛程"}
            </ActionButton>
          </>
        }
      />

      <StatStrip
        items={[
          { label: "当日比赛", value: busy ? "…" : String(rows.length), hint: `比分回传 ${matchesWithScore}/${rows.length}` },
          {
            label: "已预测",
            value: busy ? "…" : String(predictedCount),
            hint: predictedCount < rows.length ? `待补 ${rows.length - predictedCount} 场` : "已全覆盖",
            tone: predictedCount < rows.length ? "warning" : "success",
          },
          { label: "联赛覆盖", value: busy ? "…" : String(competitionsCount) },
          {
            label: "多次分析",
            value: busy ? "…" : String(multiRunFixtureCount),
            hint: registry && registry.total_tasks > 0 ? `当日任务 ${registry.completed_tasks}/${registry.total_tasks}` : "暂无编排任务",
          },
        ]}
      />

      {error ? (
        <section className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          赛程加载失败：{error}
        </section>
      ) : null}
      {predictionError ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          预测暂未加载：{predictionError}
        </section>
      ) : null}

      {selectedFixture ? (
        <SurfaceCard
          title="页内详情"
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href={`/fixtures/${selectedFixture.fixture_id}?date=${date}`}
                className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-zinc-700"
              >
                进入详情页
              </Link>
              <Link
                href={`/predictions?date=${date}&fixtureId=${selectedFixture.fixture_id}`}
                className="rounded-md border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50"
              >
                在预测页查看
              </Link>
              <button
                type="button"
                onClick={() =>
                  replaceParams((params) => {
                    params.set("date", date);
                    params.delete("fixtureId");
                  })
                }
                className="rounded-md border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-50"
              >
                关闭
              </button>
            </div>
          }
        >
          <MatchDetailCard
            fixture={selectedFixture}
            prediction={selectedPrediction}
            marketIntel={marketIntel.get(selectedFixture.fixture_id) || null}
          />
        </SurfaceCard>
      ) : null}

      {selectedFixture && selectedFixtureRuns.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-3">
          <span className="text-xs font-medium text-zinc-500">今日分析轨迹</span>
          {selectedFixtureRuns.map((run) => (
            <StatusBadge key={`${run.stage}-${run.analysis_at || "na"}-${run.task_key || "task"}`} tone={run.stage === "final" ? "success" : "warning"}>
              {run.stage_label} · {formatUpdatedAt(run.analysis_at)}
            </StatusBadge>
          ))}
        </div>
      ) : null}

      <SurfaceCard
        title="赛程"
        action={
          <button
            onClick={() => setTableCollapsed((v) => !v)}
            className="rounded-md border border-zinc-200 bg-white px-2.5 py-1 text-xs text-zinc-600 hover:bg-zinc-50"
          >
            {tableCollapsed ? "显示列表" : "隐藏列表"}
          </button>
        }
      >
        <div className="grid gap-3">
          <div className="rounded-lg border border-zinc-200 bg-zinc-50/60 px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5">
              <span className="mr-1 text-xs font-medium text-zinc-400">联赛</span>
              <Chip active={activeLeagues.length === 0} onClick={() => replaceParams((params) => params.delete("leagues"))}>
                全部
              </Chip>
              {leagueOptions.map((league) => (
                <Chip key={league} active={activeLeagues.includes(league)} onClick={() => toggleLeague(league)}>
                  {league}
                </Chip>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1.5 border-t border-zinc-200 pt-2">
              <span className="mr-1 text-xs font-medium text-zinc-400">盘口信号</span>
              <Chip active={activeSignals.length === 0} onClick={() => replaceParams((params) => params.delete("signals"))}>
                全部
              </Chip>
              {SIGNAL_FILTERS.map((filter) => {
                const count = signalCounts.get(filter.id) || 0;
                return (
                  <Chip key={filter.id} active={activeSignals.includes(filter.id)} onClick={() => toggleSignal(filter.id)}>
                    {filter.label}
                    {count > 0 ? <span className="text-zinc-400"> {count}</span> : null}
                  </Chip>
                );
              })}
              {hasActiveFilter ? (
                <button
                  onClick={() =>
                    replaceParams((params) => {
                      params.delete("leagues");
                      params.delete("signals");
                    })
                  }
                  className="ml-1 text-xs font-medium text-zinc-500 underline hover:text-zinc-900"
                >
                  清空筛选
                </button>
              ) : null}
              <span className="ml-auto text-xs text-zinc-500">
                命中 <span className="font-semibold text-zinc-900">{filteredCount}</span> / {rows.length} 场
              </span>
            </div>
          </div>

          {rows.length === 0 ? (
            <EmptyState text="当前日期还没有赛程数据，可点右上角“导入赛程”。" />
          ) : filteredCount === 0 ? (
            <EmptyState text="没有符合当前筛选条件的比赛，可清空筛选或切换日期。" />
          ) : tableCollapsed ? (
            <EmptyState text="已隐藏比赛列表，点击右上角“显示列表”恢复。" />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-zinc-200">
              <table className="w-full min-w-[1080px] border-separate border-spacing-0 text-sm">
                <thead className="sticky top-0 z-10 bg-zinc-50 text-xs text-zinc-500">
                  <tr>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">编号 / 赛事</th>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">对阵 / 开赛</th>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">官方赔率</th>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">分析批次</th>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">胜平负</th>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">让球</th>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">进球 / 比分</th>
                    <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">风险</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row, index) => {
                    const leagueName = row.competition_name_zh || competitionNameZh(row.competition_code, row.competition_name);
                    const prediction = predictions.get(row.fixture_id);
                    const fixtureSummary = fixtureLedgerMap.get(row.fixture_id);
                    const intel = marketIntel.get(row.fixture_id);
                    const handicapValue =
                      intel?.alignment?.sporttery_handicap ?? prediction?.sporttery_handicap ?? null;
                    const handicapEvaluation = evaluateSportteryHandicap(prediction, handicapValue);
                    return (
                      <tr key={row.fixture_id} className="bg-white hover:bg-zinc-50">
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                          <div className="font-semibold tabular-nums text-zinc-900">
                            {getSportteryCode(row.fixture_id, date, index)}
                          </div>
                          <span className={`mt-1 inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium ${getLeagueBadgeClass(leagueName)}`}>
                            {leagueName}
                          </span>
                        </td>
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                          <div className="font-medium text-zinc-900">
                            {row.home_team_name_zh || teamNameZh(row.home_team_name)}{" "}
                            <span className="mx-1 text-zinc-400">vs</span>{" "}
                            {row.away_team_name_zh || teamNameZh(row.away_team_name)}
                            {row.home_score != null && row.away_score != null ? (
                              <span className="ml-2 rounded bg-zinc-100 px-1.5 py-0.5 text-xs tabular-nums text-zinc-700">
                                {row.home_score}:{row.away_score}
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-1 flex items-center gap-2 text-xs text-zinc-500">
                            <span>{row.kickoff_time_zh || formatLocalTimeFromUtc(row.utc_date, "Asia/Shanghai")}</span>
                            <Link href={`/fixtures/${row.fixture_id}?date=${date}&view=analysis`} className="text-sky-600 hover:text-sky-700">
                              析
                            </Link>
                            <Link href={`/fixtures/${row.fixture_id}?date=${date}&view=news`} className="text-sky-600 hover:text-sky-700">
                              讯
                            </Link>
                          </div>
                        </td>
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top">{renderOddsChange(fixtureSummary?.odds_change)}</td>
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                          {fixtureSummary?.analysis_run_count ? (
                            <div>
                              <div className="flex flex-wrap items-center gap-1">
                                <span className="text-sm font-semibold tabular-nums text-zinc-900">{fixtureSummary.analysis_run_count} 次</span>
                                {fixtureSummary.analysis_stage_labels.map((label) => (
                                  <StatusBadge key={`${row.fixture_id}-${label}`} tone={/终版/.test(label) ? "success" : "warning"}>
                                    {label}
                                  </StatusBadge>
                                ))}
                              </div>
                              <div className="mt-1 text-xs text-zinc-400">最新 {formatUpdatedAt(fixtureSummary.latest_analysis_at)}</div>
                            </div>
                          ) : (
                            <span className="text-xs text-zinc-400">未入批次</span>
                          )}
                        </td>
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top text-zinc-700">{getOutcomeLabel(prediction)}</td>
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                          {handicapEvaluation ? (
                            <div className="flex flex-wrap items-center gap-1.5 text-sm text-zinc-800">
                              <span className="font-semibold">{handicapEvaluation.topLabel}</span>
                              <Chip tone="success">{handicapEvaluation.compactText}</Chip>
                              <span className="text-xs tabular-nums text-zinc-400">
                                {Math.round(handicapEvaluation.topProbability * 100)}%
                              </span>
                            </div>
                          ) : (
                            <span className="text-sm text-zinc-300">—</span>
                          )}
                        </td>
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                          <div className="max-w-[200px] text-zinc-700">{getGoalsScoreView(prediction)}</div>
                        </td>
                        <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                          <div className="max-w-[200px] text-zinc-600">{getRiskHint(prediction, intel)}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </SurfaceCard>

      <SurfaceCard
        title="当日分析流水"
        action={
          analysisRuns.length > 0 ? (
            <span className="text-xs text-zinc-500">
              {analysisRuns.length} 个批次 · 产出 {totalPlanCount} 个方案 · 累计 {totalStake.toFixed(0)} 元
            </span>
          ) : undefined
        }
      >
        {analysisRuns.length === 0 ? (
          <EmptyState text="当日还没有分析批次记录，通常表示今天只同步了赛程。" />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200">
            <table className="w-full border-separate border-spacing-0 text-sm">
              <thead className="bg-zinc-50 text-xs text-zinc-500">
                <tr>
                  <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">批次 / 任务</th>
                  <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">分析时间</th>
                  <th className="border-b border-zinc-200 px-3 py-2.5 text-right font-medium">在售场次</th>
                  <th className="border-b border-zinc-200 px-3 py-2.5 text-right font-medium">方案</th>
                  <th className="border-b border-zinc-200 px-3 py-2.5 text-right font-medium">投注额</th>
                  <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">固定赔率观察</th>
                  <th className="border-b border-zinc-200 px-3 py-2.5 text-left font-medium">关联方案 ID</th>
                </tr>
              </thead>
              <tbody>
                {analysisRuns.map((run) => (
                  <tr key={`${run.stage}-${run.analysis_at || "na"}`} className="bg-white">
                    <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                      <StatusBadge tone={run.stage === "final" ? "success" : "warning"}>{run.stage_label}</StatusBadge>
                      <div className="mt-1 text-xs text-zinc-400">
                        {run.task_key || "—"}
                        {run.status ? ` · ${run.status}` : ""}
                      </div>
                    </td>
                    <td className="border-b border-zinc-100 px-3 py-2.5 align-top text-zinc-700">{formatUpdatedAt(run.analysis_at)}</td>
                    <td className="border-b border-zinc-100 px-3 py-2.5 align-top text-right tabular-nums text-zinc-700">
                      {run.official_on_sale_count ?? "—"}
                    </td>
                    <td className="border-b border-zinc-100 px-3 py-2.5 align-top text-right tabular-nums text-zinc-700">{run.real_plan_count}</td>
                    <td className="border-b border-zinc-100 px-3 py-2.5 align-top text-right tabular-nums text-zinc-700">
                      {run.total_stake.toFixed(2)}
                    </td>
                    <td className="border-b border-zinc-100 px-3 py-2.5 align-top">
                      <StatusBadge tone={run.fixed_shadow_recorded ? "success" : "neutral"}>
                        {run.fixed_shadow_recorded ? run.fixed_shadow_plan_id || "已记录" : "未记录"}
                      </StatusBadge>
                    </td>
                    <td className="border-b border-zinc-100 px-3 py-2.5 align-top text-zinc-600">
                      {run.plan_ids.length > 0 ? run.plan_ids.join("、") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SurfaceCard>
    </div>
  );
}

export default function FixturesPage() {
  return (
    <Suspense fallback={<div className="py-8 text-sm text-zinc-400">比赛页加载中…</div>}>
      <FixturesPageContent />
    </Suspense>
  );
}
