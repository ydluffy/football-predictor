"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { DashboardContextResponse, Fixture, FixtureMarketIntel, Prediction, ReviewSummary } from "@/lib/api";
import {
  EmptyState,
  PageIntro,
  PrimaryLink,
  SecondaryLink,
  StatStrip,
  StatusBadge,
  SurfaceCard,
} from "@/components/Workbench";
import { getDashboardContext, getFixtures, getMarketIntel, getPredictionsByDate, getReviews } from "@/lib/api";
import { getShanghaiToday } from "@/lib/time";
import { competitionNameZh, formatLocalTimeFromUtc, teamNameZh } from "@/lib/zh";

function getMarketSignalTags(intel?: FixtureMarketIntel | null) {
  if (!intel) return [];
  const tags: Array<{ label: string; tone: "neutral" | "success" | "warning" | "danger" }> = [];
  if (intel.movement?.line_upgrade_without_price_support) tags.push({ label: "升盘背离", tone: "danger" });
  if (intel.movement?.line_downgrade) tags.push({ label: "退盘", tone: "warning" });
  if (Math.abs(intel.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5) {
    tags.push({ label: "内外盘差大", tone: "danger" });
  }
  if (intel.movement && tags.length === 0) tags.push({ label: "有盘口变化", tone: "warning" });
  if (intel.alignment?.time_aligned && tags.length === 0) tags.push({ label: "时间已对齐", tone: "success" });
  return tags;
}

function parseMatchNumberFromFixtureId(fixtureId: number) {
  const matched = String(fixtureId).trim().match(/^\d{8}(\d{3})$/);
  return matched ? matched[1] : null;
}

function formatDateTime(text?: string | null) {
  if (!text) return "—";
  return text.slice(0, 16).replace("T", " ");
}

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<DashboardContextResponse | null>(null);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [marketIntel, setMarketIntel] = useState<Map<number, FixtureMarketIntel>>(new Map());
  const [reviewSummaries, setReviewSummaries] = useState<ReviewSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const fallbackToday = useMemo(() => getShanghaiToday(), []);
  const activeSalesDay = dashboard?.active_sales_day || fallbackToday;

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const dashboardResp = await getDashboardContext();
        const [fixturesResp, predsResp, reviewsResp] = await Promise.all([
          getFixtures(dashboardResp.active_sales_day),
          getPredictionsByDate(dashboardResp.active_sales_day).catch(() => ({ count: 0, predictions: [] })),
          getReviews().catch(() => ({ summary_count: 0, plan_count: 0, summaries: [], plans: [] })),
        ]);
        const intelResp = await getMarketIntel(fixturesResp.fixtures).catch(() => ({ count: 0, items: [] }));

        if (!mounted) return;
        setDashboard(dashboardResp);
        setFixtures(fixturesResp.fixtures);
        setPredictions(predsResp.predictions);
        setMarketIntel(new Map(intelResp.items.map((item) => [item.fixture_id, item])));
        setReviewSummaries(reviewsResp.summaries || []);
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  const systemStatus = dashboard?.system_status || null;

  const coreEnvOk = useMemo(() => {
    if (!systemStatus) return false;
    return systemStatus.env.hasSupabaseUrl && systemStatus.env.hasSupabaseServiceRole;
  }, [systemStatus]);

  const optionalReadyCount = useMemo(() => {
    if (!systemStatus) return 0;
    return [
      systemStatus.env.hasFootballDataKey,
      systemStatus.env.hasOpenRouterKey,
      Boolean(systemStatus.env.hasApiFootballKey),
    ].filter(Boolean).length;
  }, [systemStatus]);

  const predictedFixtureIds = useMemo(() => new Set(predictions.map((p) => p.fixture_id)), [predictions]);

  // 战绩条：从复盘摘要直接计算（连红/累计命中率/累计ROI/上周命中）
  const heroStats = useMemo(() => {
    if (reviewSummaries.length === 0) return null;
    const totalHits = reviewSummaries.reduce((sum, item) => sum + item.hits, 0);
    const totalPlans = reviewSummaries.reduce((sum, item) => sum + item.plans, 0);
    const totalStake = reviewSummaries.reduce((sum, item) => sum + item.stake, 0);
    const totalProfit = reviewSummaries.reduce((sum, item) => sum + item.net_profit, 0);
    let streak = 0;
    for (const item of reviewSummaries) {
      if (item.net_profit > 0) streak += 1;
      else break;
    }
    const anchor = new Date(`${reviewSummaries[0].sales_day}T12:00:00+08:00`).getTime();
    const cutoff = anchor - 7 * 24 * 3600 * 1000;
    const last7Hits = reviewSummaries
      .filter((item) => new Date(`${item.sales_day}T12:00:00+08:00`).getTime() >= cutoff)
      .reduce((sum, item) => sum + item.hits, 0);
    return {
      days: reviewSummaries.length,
      totalHits,
      totalPlans,
      hitRate: totalPlans > 0 ? totalHits / totalPlans : null,
      roi: totalStake > 0 ? totalProfit / totalStake : null,
      streak,
      last7Hits,
    };
  }, [reviewSummaries]);

  // 今日流水线：注册表任务 + 隐含固定阶段
  const pipelineSteps = useMemo(() => {
    if (!dashboard) return [];
    const steps: Array<{ label: string; status: "completed" | "scheduled" | "pending" | "failed" | "info" }> = [
      { label: "10:00 预扫描", status: "info" },
      { label: "11:05 开售确认", status: dashboard.registry.total_tasks > 0 ? "completed" : "info" },
    ];
    for (const task of dashboard.registry.tasks || []) {
      const timeText = task.run_at ? task.run_at.slice(11, 16) : "--:--";
      const status =
        task.status === "completed"
          ? "completed"
          : task.status === "scheduled"
            ? "scheduled"
            : task.status === "failed"
              ? "failed"
              : "pending";
      steps.push({ label: `${timeText} ${task.purpose || task.key || "任务"}`, status });
    }
    return steps;
  }, [dashboard]);

  const predictionMap = useMemo(() => new Map(predictions.map((prediction) => [prediction.fixture_id, prediction])), [predictions]);
  const topPredictions = useMemo(
    () => predictions.filter((p) => p.confidence > 0).sort((a, b) => b.confidence - a.confidence).slice(0, 5),
    [predictions],
  );

  const keySignalFixtures = useMemo(
    () =>
      fixtures
        .map((fixture) => ({
          fixture,
          prediction: predictionMap.get(fixture.fixture_id) || null,
          tags: getMarketSignalTags(marketIntel.get(fixture.fixture_id) || null),
        }))
        .filter((item) => item.tags.length > 0)
        .sort((a, b) => {
          const aDanger = a.tags.filter((tag) => tag.tone === "danger").length;
          const bDanger = b.tags.filter((tag) => tag.tone === "danger").length;
          if (bDanger !== aDanger) return bDanger - aDanger;
          return b.tags.length - a.tags.length;
        })
        .slice(0, 5),
    [fixtures, marketIntel, predictionMap],
  );

  const planMatchNumberSet = useMemo(() => {
    const set = new Set<string>();
    for (const stage of dashboard?.betting_plans.stages || []) {
      for (const matchNumber of stage.scope || []) set.add(matchNumber);
    }
    return set;
  }, [dashboard]);

  const fallbackSignalFixtures = useMemo(
    () =>
      fixtures
        .map((fixture) => {
          const prediction = predictionMap.get(fixture.fixture_id) || null;
          const matchNumber = parseMatchNumberFromFixtureId(fixture.fixture_id);
          const tags: Array<{ label: string; tone: "neutral" | "success" | "warning" | "danger" }> = [];
          if (matchNumber && planMatchNumberSet.has(matchNumber)) tags.push({ label: "已进投注方案", tone: "danger" });
          if (prediction && prediction.confidence >= 0.45) {
            tags.push({ label: `高置信 ${Math.round(prediction.confidence * 100)}%`, tone: "warning" });
          }
          return { fixture, prediction, tags };
        })
        .filter((item) => item.tags.length > 0)
        .sort((a, b) => {
          const aPlan = a.tags.some((tag) => tag.label === "已进投注方案") ? 1 : 0;
          const bPlan = b.tags.some((tag) => tag.label === "已进投注方案") ? 1 : 0;
          if (bPlan !== aPlan) return bPlan - aPlan;
          return (b.prediction?.confidence || 0) - (a.prediction?.confidence || 0);
        })
        .slice(0, 5),
    [fixtures, planMatchNumberSet, predictionMap],
  );

  const displaySignalFixtures = keySignalFixtures.length > 0 ? keySignalFixtures : fallbackSignalFixtures;

  const spotlightPredictions = useMemo(
    () =>
      topPredictions.map((prediction) => ({
        prediction,
        fixture: fixtures.find((fixture) => fixture.fixture_id === prediction.fixture_id) || null,
        tags: getMarketSignalTags(marketIntel.get(prediction.fixture_id) || null),
      })),
    [fixtures, marketIntel, topPredictions],
  );

  const missingPredictionCount = Math.max(fixtures.length - predictions.length, 0);
  const signalNeedsReview = useMemo(
    () => displaySignalFixtures.filter((item) => !predictedFixtureIds.has(item.fixture.fixture_id)).slice(0, 4),
    [displaySignalFixtures, predictedFixtureIds],
  );

  const coreMissingEnvItems = useMemo(() => {
    if (!systemStatus) return [] as string[];
    return [
      !systemStatus.env.hasSupabaseUrl ? "SUPABASE_URL" : null,
      !systemStatus.env.hasSupabaseServiceRole ? "SUPABASE_SERVICE_ROLE_KEY" : null,
    ].filter(Boolean) as string[];
  }, [systemStatus]);

  const optionalMissingEnvItems = useMemo(() => {
    if (!systemStatus) return [] as string[];
    return [
      !systemStatus.env.hasFootballDataKey ? "FOOTBALL_DATA_API_KEY" : null,
      !systemStatus.env.hasOpenRouterKey ? "OPENROUTER_API_KEY" : null,
      !systemStatus.env.hasApiFootballKey ? "API_FOOTBALL_KEY" : null,
    ].filter(Boolean) as string[];
  }, [systemStatus]);

  const marketMode = dashboard?.market_signal_availability.mode;

  return (
    <div className="grid gap-4">
      <PageIntro
        eyebrow="总览"
        title={`${activeSalesDay} 销售日`}
        description={`销售窗至 ${formatDateTime(dashboard?.sales_window.window_end)} · 注册表更新 ${formatDateTime(dashboard?.registry.updated_at)}`}
        actions={
          <>
            <PrimaryLink href={`/predictions?date=${activeSalesDay}`}>查看预测</PrimaryLink>
            <SecondaryLink href={`/fixtures?date=${activeSalesDay}`}>查看赛程</SecondaryLink>
          </>
        }
      />

      <StatStrip
        items={[
          { label: "销售日比赛", value: loading ? "…" : String(fixtures.length) },
          {
            label: "已生成预测",
            value: loading ? "…" : String(predictions.length),
            hint: missingPredictionCount > 0 ? `待补 ${missingPredictionCount} 场` : "已全覆盖",
            tone: missingPredictionCount > 0 ? "warning" : "success",
          },
          {
            label: "今日投注方案",
            value: loading ? "…" : String(dashboard?.betting_plans.count || 0),
            hint: dashboard?.betting_plans.stages.length ? `${dashboard.betting_plans.stages.length} 个出方案阶段` : "暂无方案",
          },
          {
            label: "重点信号",
            value: loading ? "…" : String(displaySignalFixtures.length),
            hint: marketMode === "sales_day_artifacts" ? "盘口/内外盘信号" : "降级：预测与方案",
          },
        ]}
      />

      {error ? (
        <section className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          页面加载失败：{error}
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <SurfaceCard
          title="今日投注方案"
          action={
            <Link
              href={`/predictions?date=${activeSalesDay}`}
              className="text-xs font-medium text-zinc-500 hover:text-zinc-900"
            >
              进入预测页 →
            </Link>
          }
        >
          {(dashboard?.betting_plans.stages.length || 0) === 0 ? (
            <EmptyState
              text={
                dashboard?.registry.total_tasks
                  ? `今日 ${dashboard.registry.completed_tasks}/${dashboard.registry.total_tasks} 个任务已完成，尚未落地真实投注方案。`
                  : "尚未读取到已落地的投注方案。"
              }
            />
          ) : (
            <div className="divide-y divide-zinc-100">
              {dashboard?.betting_plans.stages.map((stage) => (
                <div
                  key={`${stage.stage}-${stage.analysis_at || stage.stage_label}`}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-zinc-900">{stage.stage_label}</div>
                    <div className="mt-0.5 text-xs text-zinc-500">
                      覆盖 {stage.scope.join("、") || "—"} · {formatDateTime(stage.analysis_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge tone={stage.real_plan_count > 0 ? "success" : "neutral"}>
                      {stage.real_plan_count > 0 ? `${stage.real_plan_count} 个方案` : "无方案"}
                    </StatusBadge>
                    <span className="text-sm tabular-nums text-zinc-700">{stage.total_stake.toFixed(0)} 元</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SurfaceCard>

        <SurfaceCard
          title="今日流水线"
          action={
            <Link href="/controller" className="text-xs font-medium text-zinc-500 hover:text-zinc-900">
              进入总控 →
            </Link>
          }
        >
          {pipelineSteps.length <= 2 ? (
            <EmptyState text="今日尚未生成编排任务，通常表示 11:05 开售确认还没运行。" />
          ) : (
            <div>
              <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
                {pipelineSteps.map((step, index) => (
                  <div key={`${step.label}-${index}`} className="flex items-center gap-1.5">
                    <StatusBadge
                      tone={
                        step.status === "completed"
                          ? "success"
                          : step.status === "failed"
                            ? "danger"
                            : step.status === "pending"
                              ? "warning"
                              : step.status === "scheduled"
                                ? "info"
                                : "neutral"
                      }
                    >
                      {step.label}
                    </StatusBadge>
                    {index < pipelineSteps.length - 1 ? <span className="text-zinc-300">›</span> : null}
                  </div>
                ))}
              </div>
              <div className="mt-3 border-t border-zinc-100 pt-2 text-xs text-zinc-500">
                {dashboard?.registry.next_run_at
                  ? `下一步 ${formatDateTime(dashboard.registry.next_run_at)} ${dashboard.registry.next_task_key || ""}`
                  : "当日任务已全部完成，下次唤醒为次日 10:00。"}
              </div>
            </div>
          )}
        </SurfaceCard>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <SurfaceCard
          title="重点信号比赛"
          description={marketMode === "sales_day_artifacts" ? undefined : "市场信号缺失，已降级为方案与高置信预测"}
          action={
            <Link
              href={`/fixtures?date=${activeSalesDay}`}
              className="text-xs font-medium text-zinc-500 hover:text-zinc-900"
            >
              进入比赛页 →
            </Link>
          }
        >
          {displaySignalFixtures.length === 0 ? (
            <EmptyState text="今日没有触发盘口信号或高置信条件的比赛。" />
          ) : (
            <div className="divide-y divide-zinc-100">
              {displaySignalFixtures.map((item) => {
                const fixture = item.fixture;
                const prediction = predictionMap.get(fixture.fixture_id) || null;
                const topOutcome = prediction
                  ? [
                      { label: "主胜", value: prediction.p_home },
                      { label: "平", value: prediction.p_draw },
                      { label: "客胜", value: prediction.p_away },
                    ].sort((a, b) => b.value - a.value)[0]
                  : null;
                return (
                  <Link
                    key={fixture.fixture_id}
                    href={`/fixtures/${fixture.fixture_id}?date=${activeSalesDay}`}
                    className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0 hover:bg-zinc-50"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-zinc-900">
                        {(fixture.home_team_name_zh || teamNameZh(fixture.home_team_name)) || "主队"}{" "}
                        <span className="text-zinc-400">vs</span>{" "}
                        {(fixture.away_team_name_zh || teamNameZh(fixture.away_team_name)) || "客队"}
                      </div>
                      <div className="mt-0.5 truncate text-xs text-zinc-500">
                        {fixture.competition_name_zh || competitionNameZh(fixture.competition_code, fixture.competition_name)} ·{" "}
                        {fixture.kickoff_time_zh || formatLocalTimeFromUtc(fixture.utc_date, "Asia/Shanghai")}
                        {topOutcome ? ` · 最高概率 ${topOutcome.label} ${Math.round(topOutcome.value * 100)}%` : ""}
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {prediction ? <StatusBadge tone="neutral">置信 {Math.round(prediction.confidence * 100)}%</StatusBadge> : null}
                      {item.tags.map((tag) => (
                        <StatusBadge key={tag.label} tone={tag.tone}>
                          {tag.label}
                        </StatusBadge>
                      ))}
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </SurfaceCard>

        <SurfaceCard
          title="重点预测"
          action={
            <Link
              href={`/predictions?date=${activeSalesDay}`}
              className="text-xs font-medium text-zinc-500 hover:text-zinc-900"
            >
              进入预测页 →
            </Link>
          }
        >
          {spotlightPredictions.length === 0 ? (
            <EmptyState text="今日还没有返回预测结果。" />
          ) : (
            <div className="divide-y divide-zinc-100">
              {spotlightPredictions.map(({ prediction, fixture, tags }) => {
                const topOutcome = [
                  { label: "主胜", value: prediction.p_home },
                  { label: "平", value: prediction.p_draw },
                  { label: "客胜", value: prediction.p_away },
                ].sort((a, b) => b.value - a.value)[0];
                return (
                  <Link
                    key={prediction.fixture_id}
                    href={`/fixtures/${prediction.fixture_id}?date=${activeSalesDay}`}
                    className="flex flex-wrap items-center justify-between gap-2 py-2.5 first:pt-0 last:pb-0 hover:bg-zinc-50"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-zinc-900">
                        {(fixture?.home_team_name_zh || teamNameZh(fixture?.home_team_name)) || "主队"}{" "}
                        <span className="text-zinc-400">vs</span>{" "}
                        {(fixture?.away_team_name_zh || teamNameZh(fixture?.away_team_name)) || "客队"}
                      </div>
                      <div className="mt-0.5 truncate text-xs text-zinc-500">
                        {fixture?.competition_name_zh || competitionNameZh(fixture?.competition_code, fixture?.competition_name)} · 最高概率{" "}
                        {topOutcome.label} {Math.round(topOutcome.value * 100)}%
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StatusBadge tone="neutral">置信 {Math.round(prediction.confidence * 100)}%</StatusBadge>
                      {tags.map((tag) => (
                        <StatusBadge key={tag.label} tone={tag.tone}>
                          {tag.label}
                        </StatusBadge>
                      ))}
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </SurfaceCard>
      </div>

      {heroStats ? (
        <SurfaceCard
          title="战绩速览"
          action={
            <Link href="/review" className="text-xs font-medium text-zinc-500 hover:text-zinc-900">
              查看复盘 →
            </Link>
          }
        >
          <StatStrip
            items={[
              {
                label: "当前连红",
                value: `${heroStats.streak} 天`,
                hint: "连续盈利销售日",
                tone: heroStats.streak > 0 ? "success" : undefined,
              },
              {
                label: "累计命中",
                value: `${heroStats.totalHits} 场`,
                hint: heroStats.hitRate != null ? `命中率 ${Math.round(heroStats.hitRate * 100)}%` : "—",
              },
              {
                label: "累计盈利率",
                value: heroStats.roi != null ? `${(heroStats.roi * 100).toFixed(1)}%` : "—",
                hint: "真实方案口径",
                tone: heroStats.roi != null ? (heroStats.roi > 0 ? "success" : "danger") : undefined,
              },
              { label: "近 7 日命中", value: `${heroStats.last7Hits} 场`, hint: `已复盘 ${heroStats.days} 天` },
            ]}
          />
        </SurfaceCard>
      ) : null}

      <SurfaceCard title="系统与待办">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          <StatusBadge tone={coreEnvOk ? "success" : "danger"}>{coreEnvOk ? "核心环境 2/2" : "核心环境未就绪"}</StatusBadge>
          <StatusBadge tone={optionalReadyCount === 3 ? "success" : "warning"}>可选能力 {optionalReadyCount}/3</StatusBadge>
          <StatusBadge
            tone={systemStatus?.supabase.ok ? "success" : systemStatus?.supabase.ok === false ? "danger" : "neutral"}
          >
            {systemStatus?.supabase.ok ? "数据库正常" : systemStatus?.supabase.ok === false ? "数据库异常" : "数据库待检测"}
          </StatusBadge>
          <StatusBadge tone={missingPredictionCount > 0 ? "warning" : "success"}>
            {missingPredictionCount > 0 ? `待补预测 ${missingPredictionCount} 场` : "预测已覆盖"}
          </StatusBadge>
          <StatusBadge tone={signalNeedsReview.length > 0 ? "warning" : "success"}>
            {signalNeedsReview.length > 0 ? `重点信号待查看 ${signalNeedsReview.length} 场` : "重点信号已查看"}
          </StatusBadge>
        </div>
        {coreMissingEnvItems.length > 0 || optionalMissingEnvItems.length > 0 || systemStatus?.supabase.error ? (
          <div className="mt-3 grid gap-1 text-xs">
            {coreMissingEnvItems.length > 0 ? (
              <div className="text-red-600">核心缺失：{coreMissingEnvItems.join("、")}，请到系统页补齐。</div>
            ) : null}
            {optionalMissingEnvItems.length > 0 ? (
              <div className="text-amber-600">可选未配（不影响主流程）：{optionalMissingEnvItems.join("、")}</div>
            ) : null}
            {systemStatus?.supabase.error ? <div className="text-red-600">{systemStatus.supabase.error}</div> : null}
          </div>
        ) : null}
      </SurfaceCard>
    </div>
  );
}
