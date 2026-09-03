"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import type { Fixture, FixtureMarketIntel, Prediction } from "@/lib/api";
import { getFixtures, getMarketIntel, getPredictionsByDate, ingestFootballData } from "@/lib/api";
import { MatchDetailCard } from "@/components/MatchDetailCard";
import {
  ActionButton,
  EmptyState,
  MetricCard,
  PageIntro,
  PrimaryLink,
  SecondaryLink,
  StatusBadge,
  SurfaceCard,
} from "@/components/Workbench";
import { getShanghaiToday } from "@/lib/time";
import { competitionNameZh, formatLocalTimeFromUtc, teamNameZh } from "@/lib/zh";
import { evaluateSportteryHandicap } from "@/lib/handicap";

const SIGNAL_FILTERS = [
  { id: "movement", label: "有盘口变化", hint: "存在外盘初盘和最新盘口信息" },
  { id: "upgrade_divergence", label: "升盘背离", hint: "升盘但价格未同步支持" },
  { id: "downgrade", label: "存在退盘", hint: "盘口出现退盘信号" },
  { id: "aligned_only", label: "时间已对齐", hint: "体彩与外盘满足时间对齐" },
  { id: "large_gap", label: "内外盘差较大", hint: "内外盘差值绝对值不小于 0.5" },
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
  return "bg-zinc-600 text-white";
}

function getRiskHint(pred?: Prediction | null, intel?: FixtureMarketIntel | null) {
  // 1) 体彩分析产物里已有“风险备注”时，优先使用（最接近票面表达）
  if (pred?.risk_note) return pred.risk_note;

  // 2) 没有任何市场/对齐数据，说明 market-intel 还没同步到这场
  if (!intel) return "暂无市场信号数据";

  // 3) 有明确风险信号时，给出明确结论
  if (intel.movement?.line_upgrade_without_price_support) return "升盘背离，注意热度风险";
  if (intel.movement?.line_downgrade) return "存在退盘，谨防方向反复";
  if (Math.abs(intel.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5) {
    const diff = intel.alignment?.sporttery_minus_outer_handicap_median ?? 0;
    return `内外盘差 ${diff > 0 ? "+" : ""}${diff.toFixed(2)}，注意盘口分歧`;
  }

  // 4) 有数据但没有触发明显风险时，不要用“常规观察”这种像模板的词
  if (intel.alignment?.time_aligned) return "无显著风险信号（已完成时间对齐）";
  if (intel.movement) return "无显著风险信号（存在盘口变化）";
  return "无显著风险信号";
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
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [tableCollapsed, setTableCollapsed] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);

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
  const liveCount = useMemo(
    () =>
      rows.filter((r) =>
        ["IN_PLAY", "LIVE", "PAUSED"].includes((r.status || "").toUpperCase()),
      ).length,
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

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="竞彩"
        title="足球竞猜赛程"
        description="参考体彩赛程页的阅读方式：先用紧凑筛选定位赛事，再在主表直接查看比赛编号、开赛时间、胜平负/让球方向、进球比分与风险。"
        actions={
          <>
            <PrimaryLink href={`/predictions?date=${date}`}>查看预测</PrimaryLink>
            <SecondaryLink href="/review">查看复盘</SecondaryLink>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="当日比赛" value={busy ? "…" : String(rows.length)} hint="当前选择日期的比赛总数" />
        <MetricCard label="已预测" value={busy ? "…" : String(predictedCount)} hint="已经生成胜平负结论的场次" />
        <MetricCard label="联赛覆盖" value={busy ? "…" : String(competitionsCount)} hint="当日涉及的赛事数量" />
        <MetricCard
          label="比分回传"
          value={busy ? "…" : `${matchesWithScore}/${rows.length}`}
          hint={activeSignals.length > 0 ? "当前已按盘口信号筛选" : `进行中 ${liveCount} 场`}
        />
      </section>

      {error ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          赛程加载失败：{error}
        </section>
      ) : null}
      {predictionError ? (
        <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          预测暂未加载：{predictionError}
        </section>
      ) : null}

      <SurfaceCard
        title="赛事筛选"
        description="筛选区尽量收紧，比赛信息主表优先展示；需要更多筛选时再展开。"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                replaceParams((params) => {
                  params.set("date", e.target.value);
                  params.delete("league");
                  params.delete("fixtureId");
                });
              }}
              className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
            />
            <ActionButton tone="secondary" onClick={load} disabled={busy}>
              刷新
            </ActionButton>
            <ActionButton onClick={ingest} disabled={busy}>
              {busy ? "处理中…" : "导入当日赛程"}
            </ActionButton>
          </div>
        }
      >
        {selectedFixture ? (
          <div className="mb-4">
            <MatchDetailCard
              fixture={selectedFixture}
              prediction={selectedPrediction}
              marketIntel={marketIntel.get(selectedFixture.fixture_id) || null}
              actions={
                <>
                  <Link
                    href={`/fixtures/${selectedFixture.fixture_id}?date=${date}`}
                    className="rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white"
                  >
                    进入详情页
                  </Link>
                  <Link
                    href={`/predictions?date=${date}&fixtureId=${selectedFixture.fixture_id}`}
                    className="rounded-xl border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                  >
                    在预测页查看这场比赛
                  </Link>
                  <button
                    onClick={() =>
                      replaceParams((params) => {
                        params.set("date", date);
                        params.delete("fixtureId");
                      })
                    }
                    className="rounded-xl border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                  >
                    关闭详情
                  </button>
                </>
              }
            />
          </div>
        ) : null}
        <div className="grid gap-4">
          <section className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="text-zinc-700">
                查询结果：共 <span className="font-semibold text-zinc-950">{filteredRows.length}</span> 场赛事符合条件
                <span className="ml-2 text-zinc-500">更新时间：{formatUpdatedAt(lastUpdatedAt)}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <button
                    onClick={() => setFiltersOpen((v) => !v)}
                    className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
                  >
                    赛事筛选
                    <span className="text-zinc-400">{filtersOpen ? "▴" : "▾"}</span>
                  </button>

                  {filtersOpen ? (
                    <div className="absolute left-0 top-10 z-30 w-[680px] max-w-[calc(100vw-2rem)] rounded-2xl border border-zinc-200 bg-white p-4 shadow-xl">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-zinc-900">赛事筛选</div>
                          <div className="mt-1 text-xs text-zinc-500">默认“全部”，按需勾选；点右上角可关闭。</div>
                        </div>
                        <button
                          onClick={() => setFiltersOpen(false)}
                          className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-zinc-200 text-zinc-600 hover:bg-zinc-50"
                          aria-label="关闭筛选"
                        >
                          ×
                        </button>
                      </div>

                      <div className="mt-4 grid gap-5">
                        <div>
                          <div className="text-xs font-semibold text-zinc-700">按赛事筛选</div>
                          <div className="mt-2 grid grid-cols-3 gap-2">
                            <label className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-zinc-50">
                              <input
                                type="checkbox"
                                checked={activeLeagues.length === 0}
                                onChange={() =>
                                  replaceParams((params) => {
                                    params.delete("leagues");
                                  })
                                }
                                className="h-4 w-4 rounded border-zinc-300"
                              />
                              <span className="text-sm text-zinc-700">全部</span>
                            </label>
                            {leagueOptions.map((league) => {
                              const active = activeLeagues.includes(league);
                              return (
                                <label
                                  key={league}
                                  className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-zinc-50"
                                >
                                  <input
                                    type="checkbox"
                                    checked={active}
                                    onChange={() =>
                                      replaceParams((params) => {
                                        const current = new Set(activeLeagues);
                                        if (active) current.delete(league);
                                        else current.add(league);
                                        if (current.size > 0) params.set("leagues", [...current].join(","));
                                        else params.delete("leagues");
                                      })
                                    }
                                    className="h-4 w-4 rounded border-zinc-300"
                                  />
                                  <span className="text-sm text-zinc-700">{league}</span>
                                </label>
                              );
                            })}
                          </div>
                        </div>

                        <div>
                          <div className="text-xs font-semibold text-zinc-700">按盘口信号筛选</div>
                          <div className="mt-2 grid grid-cols-3 gap-2">
                            <label className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-zinc-50">
                              <input
                                type="checkbox"
                                checked={activeSignals.length === 0}
                                onChange={() =>
                                  replaceParams((params) => {
                                    params.delete("signals");
                                  })
                                }
                                className="h-4 w-4 rounded border-zinc-300"
                              />
                              <span className="text-sm text-zinc-700">全部</span>
                            </label>
                            {SIGNAL_FILTERS.map((filter) => {
                              const active = activeSignals.includes(filter.id);
                              const count = signalCounts.get(filter.id) || 0;
                              return (
                                <label
                                  key={filter.id}
                                  className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-zinc-50"
                                >
                                  <input
                                    type="checkbox"
                                    checked={active}
                                    onChange={() =>
                                      replaceParams((params) => {
                                        const current = new Set(activeSignals);
                                        if (active) current.delete(filter.id);
                                        else current.add(filter.id);
                                        if (current.size > 0) params.set("signals", [...current].join(","));
                                        else params.delete("signals");
                                      })
                                    }
                                    className="h-4 w-4 rounded border-zinc-300"
                                  />
                                  <span className="text-sm text-zinc-700">
                                    {filter.label}
                                    {count > 0 ? <span className="ml-1 text-xs text-zinc-400">({count})</span> : null}
                                  </span>
                                </label>
                              );
                            })}
                          </div>
                        </div>

                        {(activeSignals.length > 0 || activeLeagues.length > 0) && (
                          <div className="flex items-center justify-between gap-3 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2">
                            <div className="text-xs text-zinc-600">
                              当前已筛选：
                              {activeLeagues.length > 0 ? ` 联赛 ${activeLeagues.length} 项` : ""}
                              {activeLeagues.length > 0 && activeSignals.length > 0 ? "；" : ""}
                              {activeSignals.length > 0 ? ` 信号 ${activeSignals.length} 项` : ""}
                            </div>
                            <button
                              onClick={() =>
                                replaceParams((params) => {
                                  params.delete("leagues");
                                  params.delete("signals");
                                })
                              }
                              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
                            >
                              清空筛选
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : null}
                </div>

                <button
                  onClick={() => setTableCollapsed((v) => !v)}
                  className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
                >
                  {tableCollapsed ? "显示" : "隐藏"}
                </button>
              </div>
            </div>

          </section>

          {rows.length === 0 ? (
            <EmptyState text="当前日期还没有赛程数据。可以先点击右上角“导入当日赛程”，再回来核对比赛列表。" />
          ) : filteredCount === 0 ? (
            <EmptyState text="当前日期有比赛，但没有符合所选盘口信号的场次。你可以清空筛选，或切换到其他日期继续查看。" />
          ) : tableCollapsed ? (
            <div className="rounded-2xl border border-zinc-200 bg-white px-4 py-4 text-sm text-zinc-600">
              已隐藏比赛信息栏。点击上方“显示”恢复列表。
            </div>
          ) : (
            <section className="grid gap-3">
              <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm">
                <span className="font-semibold text-orange-600">{getWeekLabel(date)} {date}</span>
                <span className="ml-2 text-zinc-700">共 {filteredRows.length} 场比赛</span>
                <span className="ml-2 text-zinc-400">(比赛编号日期：{date.replace(/-/g, "").slice(2)})</span>
              </div>
              <div className="overflow-x-auto rounded-2xl border border-zinc-200">
                <table className="min-w-[1220px] w-full border-separate border-spacing-0 text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-100 text-xs text-slate-600">
                    <tr>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">赛事编号</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">联赛</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">主队 vs 客队</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">比赛开始时间</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">比赛资讯</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">预测状态</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">胜平负预测</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">让球预测</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">进球/比分</th>
                      <th className="border-b border-zinc-200 px-3 py-3 text-left">风险</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((row, index) => {
                      const leagueName = row.competition_name_zh || competitionNameZh(row.competition_code, row.competition_name);
                      const prediction = predictions.get(row.fixture_id);
                      const intel = marketIntel.get(row.fixture_id);
                      const hasPrediction = Boolean(prediction);
                      const handicapValue =
                        intel?.alignment?.sporttery_handicap ?? prediction?.sporttery_handicap ?? null;
                      const handicapEvaluation = evaluateSportteryHandicap(prediction, handicapValue);
                      return (
                        <tr key={row.fixture_id} className="bg-white hover:bg-zinc-50">
                          <td className="border-b border-zinc-200 px-3 py-3 align-top font-medium text-zinc-900">
                            {getSportteryCode(row.fixture_id, date, index)}
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top">
                            <span className={`inline-flex rounded-lg px-3 py-1 text-xs font-semibold ${getLeagueBadgeClass(leagueName)}`}>
                              {leagueName}
                            </span>
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top">
                            <div className="font-semibold text-zinc-950">
                              {row.home_team_name_zh || teamNameZh(row.home_team_name)} <span className="mx-2 text-zinc-400">VS</span>{" "}
                              {row.away_team_name_zh || teamNameZh(row.away_team_name)}
                            </div>
                            {row.home_score != null && row.away_score != null ? (
                              <div className="mt-1 text-xs text-zinc-500">当前比分 {row.home_score}:{row.away_score}</div>
                            ) : null}
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">
                            {row.kickoff_time_zh || formatLocalTimeFromUtc(row.utc_date, "Asia/Shanghai")}
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top">
                            <div className="flex flex-wrap items-center gap-2">
                              <Link
                                href={`/fixtures/${row.fixture_id}?date=${date}&view=analysis`}
                                className="text-sm text-blue-600 hover:text-blue-700"
                              >
                                析
                              </Link>
                              <Link
                                href={`/fixtures/${row.fixture_id}?date=${date}&view=news`}
                                className="text-sm text-blue-600 hover:text-blue-700"
                              >
                                讯
                              </Link>
                            </div>
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top">
                            <StatusBadge tone={hasPrediction ? "success" : "neutral"}>{hasPrediction ? "已预测" : "未预测"}</StatusBadge>
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top text-zinc-700">{getOutcomeLabel(prediction)}</td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top">
                            {handicapEvaluation ? (
                              <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-800">
                                <span className="font-semibold">{handicapEvaluation.topLabel}</span>
                                <span className="inline-flex rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                                  {handicapEvaluation.compactText}
                                </span>
                                <span className="text-xs text-zinc-500">
                                  {Math.round(handicapEvaluation.topProbability * 100)}%
                                </span>
                              </div>
                            ) : (
                              <span className="text-sm text-zinc-500">—</span>
                            )}
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top">
                            <div className="max-w-[220px] text-zinc-700">{getGoalsScoreView(prediction)}</div>
                          </td>
                          <td className="border-b border-zinc-200 px-3 py-3 align-top">
                            <div className="max-w-[220px] text-zinc-700">{getRiskHint(prediction, intel)}</div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
        {rows.length > 0 && matchesWithScore === 0 ? (
          <div className="mt-4 text-xs text-zinc-500">提示：当前日期比赛多数尚未结束，比分为空属于正常情况。</div>
        ) : null}
      </SurfaceCard>
    </div>
  );
}

export default function FixturesPage() {
  return (
    <Suspense fallback={<div className="py-8 text-sm text-zinc-500">比赛页加载中…</div>}>
      <FixturesPageContent />
    </Suspense>
  );
}

