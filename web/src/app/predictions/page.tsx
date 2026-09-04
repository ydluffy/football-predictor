"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import type { Fixture, FixtureMarketIntel, Prediction } from "@/lib/api";
import { getFixtures, getMarketIntel, getPredictionsByDate, ingestFootballData } from "@/lib/api";
import { MatchDetailCard } from "@/components/MatchDetailCard";
import { ProbBar } from "@/components/ProbBar";
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

function getMarketSignalTags(intel?: FixtureMarketIntel | null) {
  if (!intel) return [];
  const tags: Array<{ label: string; tone: "neutral" | "success" | "warning" | "danger" }> = [];
  if (intel.movement) {
    tags.push({ label: "有盘口变化", tone: "warning" });
  }
  if (intel.movement?.line_upgrade_without_price_support) {
    tags.push({ label: "升盘背离", tone: "danger" });
  }
  if (intel.movement?.line_downgrade) {
    tags.push({ label: "存在退盘", tone: "warning" });
  }
  if (intel.alignment?.time_aligned) {
    tags.push({ label: "时间已对齐", tone: "success" });
  }
  if (Math.abs(intel.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5) {
    tags.push({ label: "内外盘差较大", tone: "danger" });
  }
  return tags;
}

function PredictionsPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [date, setDate] = useState(getShanghaiToday());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [preds, setPreds] = useState<Prediction[]>([]);
  const [marketIntel, setMarketIntel] = useState<Map<number, FixtureMarketIntel>>(new Map());

  const selectedFixtureId = useMemo(() => {
    const raw = searchParams.get("fixtureId");
    return raw ? Number(raw) : null;
  }, [searchParams]);

  const pushParams = useCallback(
    (nextDate: string, fixtureId?: number | null) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("date", nextDate);
      if (fixtureId != null) {
        params.set("fixtureId", String(fixtureId));
      } else {
        params.delete("fixtureId");
      }
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const load = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const f = await getFixtures(date);
      setFixtures(f.fixtures);
      try {
        const intel = await getMarketIntel(f.fixtures);
        setMarketIntel(new Map(intel.items.map((item) => [item.fixture_id, item])));
      } catch {
        setMarketIntel(new Map());
      }
      const p = await getPredictionsByDate(date);
      setPreds(p.predictions);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPreds([]);
      setMarketIntel(new Map());
    } finally {
      setBusy(false);
    }
  }, [date]);

  async function ingestAndLoad() {
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

  const byId = useMemo(() => {
    const m = new Map<number, Fixture>();
    for (const f of fixtures) m.set(f.fixture_id, f);
    return m;
  }, [fixtures]);
  const orderedPreds = useMemo(
    () => [...preds].sort((a, b) => b.confidence - a.confidence),
    [preds],
  );
  const highConfidenceCount = useMemo(
    () => orderedPreds.filter((p) => p.confidence >= 0.65).length,
    [orderedPreds],
  );
  const withBettingAdvice = useMemo(
    () => orderedPreds.filter((p) => Boolean(p.betting_recommendation)).length,
    [orderedPreds],
  );
  const avgConfidence = useMemo(() => {
    if (orderedPreds.length === 0) return "—";
    const value = orderedPreds.reduce((sum, item) => sum + item.confidence, 0) / orderedPreds.length;
    return `${Math.round(value * 100)}%`;
  }, [orderedPreds]);
  const withMarketSignals = useMemo(
    () => orderedPreds.filter((prediction) => getMarketSignalTags(marketIntel.get(prediction.fixture_id)).length > 0).length,
    [marketIntel, orderedPreds],
  );
  const selectedFixture = useMemo(
    () => fixtures.find((fixture) => fixture.fixture_id === selectedFixtureId) || null,
    [fixtures, selectedFixtureId],
  );
  const selectedPrediction = useMemo(
    () => orderedPreds.find((prediction) => prediction.fixture_id === selectedFixtureId) || null,
    [orderedPreds, selectedFixtureId],
  );

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="预测工作页"
        title="把概率、信心和可读解释放在同一张卡里"
        description="当前仍以泊松基线为主，但这一页已经按照真正工作台来组织信息：先看数量和覆盖，再看每场比赛的主胜平客胜、Top 比分、大小球和价值投注说明。"
        actions={
          <>
            <PrimaryLink href={`/fixtures?date=${date}`}>查看比赛</PrimaryLink>
            <SecondaryLink href="/chat">让助手解释</SecondaryLink>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="预测场次" value={busy ? "…" : String(orderedPreds.length)} hint="当前日期返回的预测结果数" />
        <MetricCard label="高置信比赛" value={busy ? "…" : String(highConfidenceCount)} hint="置信度大于等于 65%" />
        <MetricCard label="平均置信度" value={busy ? "…" : avgConfidence} hint="用于快速判断整体可读性" />
        <MetricCard
          label="市场信号"
          value={busy ? "…" : String(withMarketSignals)}
          hint={`投注建议 ${withBettingAdvice} 场，市场侧有提示的比赛数`}
        />
      </section>

      {error ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          预测加载失败：{error}
        </section>
      ) : null}

      <SurfaceCard
        title="预测列表"
        description="数据来源：`/api/predictions`。如果当天数据还没准备好，可以直接执行导入并刷新。"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                pushParams(e.target.value, selectedFixtureId);
              }}
              className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
            />
            <ActionButton tone="secondary" onClick={load} disabled={busy}>
              刷新
            </ActionButton>
            <ActionButton onClick={ingestAndLoad} disabled={busy}>
              {busy ? "处理中…" : "导入并刷新"}
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
                    href={`/fixtures?date=${date}&fixtureId=${selectedFixture.fixture_id}`}
                    className="rounded-xl border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                  >
                    回到比赛页
                  </Link>
                  <button
                    onClick={() => pushParams(date, null)}
                    className="rounded-xl border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                  >
                    关闭详情
                  </button>
                </>
              }
            />
          </div>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2">
          {orderedPreds.length === 0 ? (
            <EmptyState text="当前日期还没有预测结果。通常是赛程未导入，或预测接口尚未返回数据。" />
          ) : (
            orderedPreds.map((p) => {
              const fx = byId.get(p.fixture_id);
              const intel = marketIntel.get(p.fixture_id);
              const signalTags = getMarketSignalTags(intel);
              const handicapValue = intel?.alignment?.sporttery_handicap ?? p.sporttery_handicap ?? null;
              const handicapEvaluation = evaluateSportteryHandicap(p, handicapValue);
              const topOutcome = [
                { label: "主胜", value: p.p_home },
                { label: "平", value: p.p_draw },
                { label: "客胜", value: p.p_away },
              ].sort((a, b) => b.value - a.value)[0];

              return (
                <article
                  key={p.fixture_id}
                  className={
                    selectedFixtureId === p.fixture_id
                      ? "rounded-2xl border border-zinc-900 bg-white p-4 shadow-sm"
                      : "rounded-2xl border border-zinc-200 bg-white p-4"
                  }
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-zinc-950">
                        {(fx?.home_team_name_zh || teamNameZh(fx?.home_team_name)) || "主队"} vs{" "}
                        {(fx?.away_team_name_zh || teamNameZh(fx?.away_team_name)) || "客队"}
                      </div>
                      <div className="mt-0.5 text-xs text-zinc-500">
                        {fx?.competition_name_zh || competitionNameZh(fx?.competition_code, fx?.competition_name)} ·{" "}
                        {fx?.kickoff_time_zh || formatLocalTimeFromUtc(fx?.utc_date, "Asia/Shanghai")}
                        <span className="ml-2 text-zinc-400">UTC {fx?.utc_date?.slice(11, 16) || "-"}</span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <StatusBadge tone={p.confidence >= 0.65 ? "success" : "neutral"}>
                        置信 {Math.round(p.confidence * 100)}%
                      </StatusBadge>
                      <StatusBadge tone="warning">
                        最高概率 {topOutcome.label} {Math.round(topOutcome.value * 100)}%
                      </StatusBadge>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-2">
                    <ProbBar label="主胜" value={p.p_home} />
                    <ProbBar label="平" value={p.p_draw} />
                    <ProbBar label="客胜" value={p.p_away} />
                  </div>

                  {signalTags.length > 0 ? (
                    <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-3">
                      <div className="text-xs font-semibold text-amber-950">市场信号</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {signalTags.map((tag) => (
                          <StatusBadge key={tag.label} tone={tag.tone}>
                            {tag.label}
                          </StatusBadge>
                        ))}
                      </div>
                      <div className="mt-2 text-xs text-amber-900">
                        {intel?.movement?.home_line_strength_delta != null ? (
                          <span>
                            盘口强度 {intel.movement.home_line_strength_delta > 0 ? "+" : ""}
                            {intel.movement.home_line_strength_delta.toFixed(2)}
                          </span>
                        ) : null}
                        {intel?.alignment?.sporttery_minus_outer_handicap_median != null ? (
                          <span className={intel?.movement?.home_line_strength_delta != null ? "ml-3" : ""}>
                            内外盘差 {intel.alignment.sporttery_minus_outer_handicap_median > 0 ? "+" : ""}
                            {intel.alignment.sporttery_minus_outer_handicap_median.toFixed(2)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-3 text-xs text-zinc-700">
                    <div className="font-semibold text-zinc-900">关键因素</div>
                    <ul className="mt-2 list-disc pl-5">
                      {p.factors.slice(0, 3).map((t, idx) => (
                        <li key={idx} className="leading-5">
                          {t}
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="mt-3 rounded-xl border border-zinc-200 bg-white px-3 py-3 text-xs text-zinc-700">
                    <div className="font-semibold text-zinc-900">比分与衍生玩法</div>
                    {handicapEvaluation ? (
                      <div className="mt-2">
                        让球：{handicapEvaluation.compactText} {handicapEvaluation.topLabel}（让胜{" "}
                        {Math.round(handicapEvaluation.p_let_win * 100)}% / 让平 {Math.round(handicapEvaluation.p_let_draw * 100)}% / 让负{" "}
                        {Math.round(handicapEvaluation.p_let_lose * 100)}%）
                      </div>
                    ) : null}
                    <div className="mt-2">
                      Top 比分：
                      {p.scorelines_top?.length
                        ? p.scorelines_top
                            .slice(0, 3)
                            .map((s) => `${s.home_goals}-${s.away_goals}(${Math.round(s.p * 100)}%)`)
                            .join("，")
                        : "暂无"}
                    </div>
                    <div className="mt-1">
                      大 2.5：{p.p_over_2_5 != null ? `${Math.round(p.p_over_2_5 * 100)}%` : "-"}，小 2.5：
                      {p.p_under_2_5 != null ? `${Math.round(p.p_under_2_5 * 100)}%` : "-"}，双方进球：
                      {p.p_btts_yes != null ? `${Math.round(p.p_btts_yes * 100)}%` : "-"}
                    </div>
                  </div>

                  <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-3 text-xs text-emerald-900">
                    <div className="font-semibold">价值投注建议</div>
                    <div className="mt-1">
                      {p.betting_recommendation || "当前未提供赔率或 EV/Kelly 信息。"}
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href={`/fixtures/${p.fixture_id}?date=${date}`}
                      className="rounded-xl border border-zinc-200 px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                    >
                      进入详情页
                    </Link>
                    <button
                      onClick={() => pushParams(date, p.fixture_id)}
                      className="rounded-xl border border-zinc-200 px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                    >
                      页内预览
                    </button>
                    <Link
                      href={`/fixtures?date=${date}&fixtureId=${p.fixture_id}`}
                      className="rounded-xl border border-zinc-200 px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                    >
                      回到比赛页
                    </Link>
                  </div>
                </article>
              );
            })
          )}
        </div>
      </SurfaceCard>
    </div>
  );
}

export default function PredictionsPage() {
  return (
    <Suspense fallback={<div className="py-8 text-sm text-zinc-500">预测页加载中…</div>}>
      <PredictionsPageContent />
    </Suspense>
  );
}

