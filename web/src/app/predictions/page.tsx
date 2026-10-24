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

// 只在真正触发信号时返回标签，避免"有盘口变化"这类无信息量的徽标堆满页面。
function getMarketSignalTags(intel?: FixtureMarketIntel | null) {
  if (!intel) return [];
  const tags: Array<{ label: string; tone: "warning" | "danger" | "success" }> = [];
  if (intel.movement?.line_upgrade_without_price_support) tags.push({ label: "升盘背离", tone: "danger" });
  if (intel.movement?.line_downgrade) tags.push({ label: "退盘", tone: "warning" });
  if (Math.abs(intel.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5) {
    tags.push({ label: "内外盘差大", tone: "danger" });
  }
  if (tags.length === 0 && intel.movement) tags.push({ label: "有盘口变化", tone: "warning" });
  if (tags.length === 0 && intel.alignment?.time_aligned) tags.push({ label: "时间已对齐", tone: "success" });
  return tags;
}

// 自然语言推荐口径：把概率和让球盘口翻译成一句话。
function buildRecommendationPhrase(
  prediction: Prediction,
  handicapEvaluation: ReturnType<typeof evaluateSportteryHandicap>,
) {
  const top = [
    { label: "主胜", value: prediction.p_home },
    { label: "平局", value: prediction.p_draw },
    { label: "客胜", value: prediction.p_away },
  ].sort((a, b) => b.value - a.value)[0];
  const outcomePart = `胜平负倾向${top.label}（${Math.round(top.value * 100)}%）`;
  if (!handicapEvaluation) return outcomePart;
  const handicapPart = `让球口径：${handicapEvaluation.compactText} ${handicapEvaluation.topLabel}（${Math.round(
    handicapEvaluation.topProbability * 100,
  )}%，即${handicapEvaluation.logicHint}）`;
  return `${outcomePart}；${handicapPart}`;
}

const LINK_MUTED =
  "rounded-md border border-zinc-200 px-3 py-1.5 text-xs text-zinc-600 transition hover:bg-zinc-50 hover:text-zinc-900";

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
    <div className="grid gap-5">
      <PageIntro
        eyebrow={date}
        title="预测"
        description="按销售日列出已生成的预测结论，按置信度从高到低排列。"
        actions={
          <>
            <input
              type="date"
              value={date}
              onChange={(e) => {
                setDate(e.target.value);
                pushParams(e.target.value, selectedFixtureId);
              }}
              className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-zinc-400"
            />
            <ActionButton tone="secondary" onClick={load} disabled={busy}>
              刷新
            </ActionButton>
            <ActionButton onClick={ingestAndLoad} disabled={busy}>
              {busy ? "处理中…" : "导入并刷新"}
            </ActionButton>
          </>
        }
      />

      <StatStrip
        items={[
          { label: "预测场次", value: busy ? "…" : String(orderedPreds.length) },
          { label: "高置信", value: busy ? "…" : String(highConfidenceCount), hint: "置信度 ≥ 65%" },
          { label: "平均置信度", value: busy ? "…" : avgConfidence },
          {
            label: "市场信号",
            value: busy ? "…" : String(withMarketSignals),
            hint: `含投注建议 ${withBettingAdvice} 场`,
          },
        ]}
      />

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">预测加载失败：{error}</div>
      ) : null}

      {selectedFixture ? (
        <SurfaceCard
          title="页内预览"
          action={
            <div className="flex flex-wrap items-center gap-2">
              <Link href={`/fixtures/${selectedFixture.fixture_id}?date=${date}`} className={LINK_MUTED}>
                进入详情页
              </Link>
              <button type="button" onClick={() => pushParams(date, null)} className={LINK_MUTED}>
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

      <SurfaceCard
        title="预测列表"
        action={<span className="text-xs text-zinc-400">{busy ? "加载中…" : `${orderedPreds.length} 场`}</span>}
      >
        {orderedPreds.length === 0 ? (
          <EmptyState text="当前日期没有预测结果，通常是赛程未导入或预测尚未生成。" />
        ) : (
          <div>
            {orderedPreds.map((p) => {
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
              const scoreText = p.scorelines_top?.length
                ? p.scorelines_top
                    .slice(0, 3)
                    .map((s) => `${s.home_goals}-${s.away_goals}(${Math.round(s.p * 100)}%)`)
                    .join(" ")
                : "—";
              const pct = (value?: number | null) => (value != null ? `${Math.round(value * 100)}%` : "—");

              return (
                <article key={p.fixture_id} className="border-b border-zinc-100 py-4 first:pt-0 last:border-b-0 last:pb-0">
                  <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-zinc-900">
                          {(fx?.home_team_name_zh || teamNameZh(fx?.home_team_name)) || "主队"} vs{" "}
                          {(fx?.away_team_name_zh || teamNameZh(fx?.away_team_name)) || "客队"}
                        </span>
                        {selectedFixtureId === p.fixture_id ? <Chip tone="info">预览中</Chip> : null}
                      </div>
                      <div className="mt-0.5 text-xs text-zinc-500">
                        {fx?.competition_name_zh || competitionNameZh(fx?.competition_code, fx?.competition_name)} ·{" "}
                        {fx?.kickoff_time_zh || formatLocalTimeFromUtc(fx?.utc_date, "Asia/Shanghai")}
                        <span className="ml-2 text-zinc-400">UTC {fx?.utc_date?.slice(11, 16) || "-"}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge tone={p.confidence >= 0.65 ? "success" : "neutral"}>
                        置信 {Math.round(p.confidence * 100)}%
                      </StatusBadge>
                      <span className="text-xs text-zinc-500">
                        最高概率 {topOutcome.label} {Math.round(topOutcome.value * 100)}%
                      </span>
                    </div>
                  </div>

                  <div className="mt-3 grid gap-2 md:grid-cols-3">
                    <ProbBar label="主胜" value={p.p_home} />
                    <ProbBar label="平" value={p.p_draw} />
                    <ProbBar label="客胜" value={p.p_away} />
                  </div>

                  <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
                    <span>
                      让球{" "}
                      <span className="tabular-nums text-zinc-900">
                        {handicapEvaluation ? `${handicapEvaluation.compactText} ${handicapEvaluation.topLabel}` : "—"}
                      </span>
                    </span>
                    <span>
                      Top 比分 <span className="tabular-nums text-zinc-900">{scoreText}</span>
                    </span>
                    <span>
                      大 2.5 <span className="tabular-nums text-zinc-900">{pct(p.p_over_2_5)}</span>
                    </span>
                    <span>
                      双方进球 <span className="tabular-nums text-zinc-900">{pct(p.p_btts_yes)}</span>
                    </span>
                  </div>

                  {signalTags.length > 0 || intel?.alignment?.sporttery_minus_outer_handicap_median != null ? (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {signalTags.map((tag) => (
                        <StatusBadge key={tag.label} tone={tag.tone}>
                          {tag.label}
                        </StatusBadge>
                      ))}
                      {intel?.movement?.home_line_strength_delta != null ? (
                        <span className="text-xs tabular-nums text-zinc-500">
                          盘口强度 {intel.movement.home_line_strength_delta > 0 ? "+" : ""}
                          {intel.movement.home_line_strength_delta.toFixed(2)}
                        </span>
                      ) : null}
                      {intel?.alignment?.sporttery_minus_outer_handicap_median != null ? (
                        <span className="text-xs tabular-nums text-zinc-500">
                          内外盘差 {intel.alignment.sporttery_minus_outer_handicap_median > 0 ? "+" : ""}
                          {intel.alignment.sporttery_minus_outer_handicap_median.toFixed(2)}
                        </span>
                      ) : null}
                    </div>
                  ) : null}

                  {p.factors?.length ? (
                    <ul className="mt-3 list-disc pl-4 text-xs leading-5 text-zinc-600">
                      {p.factors.slice(0, 3).map((t, idx) => (
                        <li key={idx}>{t}</li>
                      ))}
                    </ul>
                  ) : null}

                  <p className="mt-3 text-xs leading-5 text-zinc-600">
                    <span className="font-medium text-zinc-900">推荐口径</span>
                    <span className="mx-1.5 text-zinc-300">|</span>
                    {buildRecommendationPhrase(p, handicapEvaluation)}
                  </p>

                  {p.betting_recommendation ? (
                    <p className="mt-1.5 text-xs leading-5 text-emerald-700">
                      <span className="font-medium text-emerald-800">价值投注</span>
                      <span className="mx-1.5 text-emerald-300">|</span>
                      {p.betting_recommendation}
                    </p>
                  ) : null}

                  <div className="mt-3 flex flex-wrap gap-2">
                    <Link href={`/fixtures/${p.fixture_id}?date=${date}`} className={LINK_MUTED}>
                      进入详情页
                    </Link>
                    <button type="button" onClick={() => pushParams(date, p.fixture_id)} className={LINK_MUTED}>
                      页内预览
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </SurfaceCard>
    </div>
  );
}

export default function PredictionsPage() {
  return (
    <Suspense fallback={<div className="py-8 text-xs text-zinc-400">预测页加载中…</div>}>
      <PredictionsPageContent />
    </Suspense>
  );
}
