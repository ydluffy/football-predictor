"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { DashboardContextResponse, Fixture, FixtureMarketIntel, Prediction } from "@/lib/api";
import {
  EmptyState,
  MetricCard,
  PageIntro,
  PrimaryLink,
  SecondaryLink,
  StatusBadge,
  SurfaceCard,
} from "@/components/Workbench";
import { getDashboardContext, getFixtures, getMarketIntel, getPredictionsByDate } from "@/lib/api";
import { getShanghaiToday } from "@/lib/time";
import { competitionNameZh, formatLocalTimeFromUtc, teamNameZh } from "@/lib/zh";

function getMarketSignalTags(intel?: FixtureMarketIntel | null) {
  if (!intel) return [];
  const tags: Array<{ label: string; tone: "neutral" | "success" | "warning" | "danger" }> = [];
  if (intel.movement) tags.push({ label: "有盘口变化", tone: "warning" });
  if (intel.movement?.line_upgrade_without_price_support) tags.push({ label: "升盘背离", tone: "danger" });
  if (intel.movement?.line_downgrade) tags.push({ label: "存在退盘", tone: "warning" });
  if (intel.alignment?.time_aligned) tags.push({ label: "时间已对齐", tone: "success" });
  if (Math.abs(intel.alignment?.sporttery_minus_outer_handicap_median ?? 0) >= 0.5) {
    tags.push({ label: "内外盘差较大", tone: "danger" });
  }
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
        const [fixturesResp, predsResp] = await Promise.all([
          getFixtures(dashboardResp.active_sales_day),
          getPredictionsByDate(dashboardResp.active_sales_day).catch(() => ({ count: 0, predictions: [] })),
        ]);
        const intelResp = await getMarketIntel(fixturesResp.fixtures).catch(() => ({ count: 0, items: [] }));

        if (!mounted) return;
        setDashboard(dashboardResp);
        setFixtures(fixturesResp.fixtures);
        setPredictions(predsResp.predictions);
        setMarketIntel(new Map(intelResp.items.map((item) => [item.fixture_id, item])));
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
  const predictionMap = useMemo(() => new Map(predictions.map((prediction) => [prediction.fixture_id, prediction])), [predictions]);
  const readyPredictions = useMemo(
    () => predictions.filter((p) => p.confidence > 0).sort((a, b) => b.confidence - a.confidence),
    [predictions],
  );
  const topPredictions = readyPredictions.slice(0, 5);

  const keySignalFixtures = useMemo(
    () =>
      fixtures
        .map((fixture) => ({
          fixture,
          intel: marketIntel.get(fixture.fixture_id) || null,
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
    [fixtures, marketIntel],
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
          if (matchNumber && planMatchNumberSet.has(matchNumber)) {
            tags.push({ label: "已进投注方案", tone: "danger" });
          }
          if (prediction && prediction.confidence >= 0.45) {
            tags.push({ label: `高置信 ${Math.round(prediction.confidence * 100)}%`, tone: "warning" });
          }
          if (prediction && typeof prediction.sporttery_handicap === "number") {
            const sign = prediction.sporttery_handicap > 0 ? "+" : "";
            tags.push({ label: `让球 ${sign}${prediction.sporttery_handicap}`, tone: "neutral" });
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
        intel: marketIntel.get(prediction.fixture_id) || null,
        tags: getMarketSignalTags(marketIntel.get(prediction.fixture_id) || null),
      })),
    [fixtures, marketIntel, topPredictions],
  );

  const missingPredictionCount = Math.max(fixtures.length - predictions.length, 0);
  const keySignalCount = displaySignalFixtures.length;
  const missingPredictionFixtures = useMemo(
    () => fixtures.filter((fixture) => !predictedFixtureIds.has(fixture.fixture_id)).slice(0, 4),
    [fixtures, predictedFixtureIds],
  );
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

  const salesWindowText = useMemo(() => {
    if (!dashboard?.sales_window.window_end) return "未识别到体彩销售窗，已按默认口径回退。";
    return `当前按体彩销售日 ${dashboard.active_sales_day} 展示，销售窗截止 ${formatDateTime(dashboard.sales_window.window_end)}。`;
  }, [dashboard]);

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="销售日总览"
        title={`${activeSalesDay} 体彩工作台`}
        description={`首页已切到“体彩销售日”口径，不再按过了零点就清空。${salesWindowText}${dashboard?.market_signal_availability.note ? ` ${dashboard.market_signal_availability.note}` : ""}`}
        actions={
          <>
            <PrimaryLink href={`/predictions?date=${activeSalesDay}`}>查看销售日预测</PrimaryLink>
            <SecondaryLink href={`/fixtures?date=${activeSalesDay}`}>查看销售日赛程</SecondaryLink>
            <SecondaryLink href="/review">查看复盘</SecondaryLink>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="销售日比赛" value={loading ? "…" : String(fixtures.length)} hint="按体彩销售日窗口聚合" />
        <MetricCard
          label="已生成预测"
          value={loading ? "…" : String(predictions.length)}
          hint={loading ? "已返回胜平负概率的比赛数" : `仍有 ${missingPredictionCount} 场待补预测`}
        />
        <MetricCard
          label="今日投注方案"
          value={loading ? "…" : String(dashboard?.betting_plans.count || 0)}
          hint={
            loading
              ? "按早盘/终版阶段统计真实方案数"
              : dashboard?.betting_plans.stages.length
                ? `已落地 ${dashboard.betting_plans.stages.length} 个出方案阶段`
                : "当前还没有已落地的真实投注方案"
          }
        />
        <MetricCard
          label="重点信号"
          value={loading ? "…" : String(keySignalCount)}
          hint={dashboard?.market_signal_availability.mode === "sales_day_artifacts" ? "优先展示盘口/内外盘信号" : "市场信号缺失时自动降级为预测/方案重点"}
        />
      </section>

      {error ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          页面加载时发生错误：{error}
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SurfaceCard
          title="今日投注方案"
          description="把当前销售日已经真正出方案的阶段放在首页第一屏，先看有没有方案，再看方案覆盖了哪些比赛。"
          action={
            <Link href={`/predictions?date=${activeSalesDay}`} className="text-sm font-medium text-zinc-700 hover:text-zinc-950">
              进入预测页
            </Link>
          }
        >
          <div className="grid gap-3">
            {(dashboard?.betting_plans.stages.length || 0) === 0 ? (
              <EmptyState
                text={
                  dashboard?.registry.total_tasks
                    ? `当前销售日共 ${dashboard.registry.total_tasks} 个任务，已完成 ${dashboard.registry.completed_tasks} 个，暂未读取到真实投注方案产物。`
                    : "当前还没有读取到已落地的投注方案。"
                }
              />
            ) : (
              dashboard?.betting_plans.stages.map((stage) => (
                <div key={`${stage.stage}-${stage.analysis_at || stage.stage_label}`} className="rounded-xl border border-zinc-200 px-4 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-zinc-950">{stage.stage_label}</div>
                      <div className="mt-1 text-xs text-zinc-500">
                        生成时间 {formatDateTime(stage.analysis_at)} · 覆盖场次 {stage.scope.join("、") || "—"}
                      </div>
                    </div>
                    <StatusBadge tone={stage.real_plan_count > 0 ? "success" : "neutral"}>
                      {stage.real_plan_count > 0 ? `${stage.real_plan_count} 个真实方案` : "无真实方案"}
                    </StatusBadge>
                  </div>
                  <div className="mt-3 grid gap-3 text-sm text-zinc-700 md:grid-cols-3">
                    <div className="rounded-xl bg-zinc-50 px-3 py-3">
                      <div className="text-xs text-zinc-500">方案数</div>
                      <div className="mt-1 font-semibold text-zinc-950">{stage.real_plan_count}</div>
                    </div>
                    <div className="rounded-xl bg-zinc-50 px-3 py-3">
                      <div className="text-xs text-zinc-500">总投注额</div>
                      <div className="mt-1 font-semibold text-zinc-950">{stage.total_stake.toFixed(2)} 元</div>
                    </div>
                    <div className="rounded-xl bg-zinc-50 px-3 py-3">
                      <div className="text-xs text-zinc-500">影子方案</div>
                      <div className="mt-1 font-semibold text-zinc-950">{stage.fixed_shadow_recorded ? "已记录" : "未记录"}</div>
                    </div>
                  </div>
                  {stage.plan_ids.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {stage.plan_ids.map((planId) => (
                        <StatusBadge key={planId} tone={/SAFE/i.test(planId) ? "success" : "warning"}>
                          {planId}
                        </StatusBadge>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </SurfaceCard>

        <SurfaceCard
          title="今日重点信号比赛"
          description={
            dashboard?.market_signal_availability.mode === "sales_day_artifacts"
              ? "优先看盘口异常、内外盘差较大或已完成时间对齐的场次。"
              : "当前销售日缺少盘口/对齐产物，先用“已进投注方案 + 高置信预测”兜底显示重点比赛。"
          }
          action={
            <Link href={`/fixtures?date=${activeSalesDay}`} className="text-sm font-medium text-zinc-700 hover:text-zinc-950">
              进入比赛页
            </Link>
          }
        >
          <div className="grid gap-3">
            {displaySignalFixtures.length === 0 ? (
              <EmptyState text="当前没有可展示的重点信号比赛。建议先确认销售日赛程、预测与市场信号产物是否同步完成。" />
            ) : (
              displaySignalFixtures.map((item) => {
                const fixture = item.fixture;
                const prediction = predictionMap.get(fixture.fixture_id) || null;
                const tags = item.tags;
                const topOutcome = prediction
                  ? [
                      { label: "主胜", value: prediction.p_home },
                      { label: "平", value: prediction.p_draw },
                      { label: "客胜", value: prediction.p_away },
                    ].sort((a, b) => b.value - a.value)[0]
                  : null;

                return (
                  <div key={fixture.fixture_id} className="rounded-xl border border-zinc-200 px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-zinc-950">
                          {(fixture.home_team_name_zh || teamNameZh(fixture.home_team_name)) || "主队"} vs{" "}
                          {(fixture.away_team_name_zh || teamNameZh(fixture.away_team_name)) || "客队"}
                        </div>
                        <div className="mt-1 text-xs text-zinc-500">
                          {fixture.competition_name_zh || competitionNameZh(fixture.competition_code, fixture.competition_name)} ·{" "}
                          {fixture.kickoff_time_zh || formatLocalTimeFromUtc(fixture.utc_date, "Asia/Shanghai")}
                        </div>
                      </div>
                      {prediction ? (
                        <div className="rounded-full bg-zinc-100 px-3 py-1 text-xs text-zinc-700">
                          置信 {Math.round(prediction.confidence * 100)}%
                        </div>
                      ) : null}
                    </div>
                    {topOutcome ? <div className="mt-2 text-sm text-zinc-600">当前最高概率：{topOutcome.label} {Math.round(topOutcome.value * 100)}%</div> : null}
                    {tags.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {tags.map((tag) => (
                          <StatusBadge key={tag.label} tone={tag.tone}>
                            {tag.label}
                          </StatusBadge>
                        ))}
                      </div>
                    ) : null}
                    {prediction ? <div className="mt-2 text-xs text-zinc-500 line-clamp-2">{(prediction.factors || []).slice(0, 2).join("；") || "暂无关键因素说明"}</div> : null}
                    <div className="mt-3">
                      <Link href={`/fixtures/${fixture.fixture_id}?date=${activeSalesDay}`} className="text-xs font-medium text-zinc-700 hover:text-zinc-950">
                        进入单场详情
                      </Link>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </SurfaceCard>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_0.95fr]">
        <SurfaceCard
          title="今日重点预测比赛"
          description="把高置信度预测放在一起，作为首页第二层的重点关注区。"
          action={
            <Link href={`/predictions?date=${activeSalesDay}`} className="text-sm font-medium text-zinc-700 hover:text-zinc-950">
              进入预测页
            </Link>
          }
        >
          <div className="grid gap-3">
            {spotlightPredictions.length === 0 ? (
              <EmptyState text="还没有可展示的预测结果，通常是因为销售日数据未导入，或预测接口尚未返回数据。" />
            ) : (
              spotlightPredictions.map(({ prediction, fixture, tags }) => {
                const topOutcome = [
                  { label: "主胜", value: prediction.p_home },
                  { label: "平", value: prediction.p_draw },
                  { label: "客胜", value: prediction.p_away },
                ].sort((a, b) => b.value - a.value)[0];

                return (
                  <div key={prediction.fixture_id} className="rounded-xl border border-zinc-200 px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-zinc-950">
                          {(fixture?.home_team_name_zh || teamNameZh(fixture?.home_team_name)) || "主队"} vs{" "}
                          {(fixture?.away_team_name_zh || teamNameZh(fixture?.away_team_name)) || "客队"}
                        </div>
                        <div className="mt-1 text-xs text-zinc-500">
                          {fixture?.competition_name_zh || competitionNameZh(fixture?.competition_code, fixture?.competition_name)} ·{" "}
                          {fixture?.kickoff_time_zh || formatLocalTimeFromUtc(fixture?.utc_date, "Asia/Shanghai")}
                        </div>
                      </div>
                      <div className="rounded-full bg-zinc-100 px-3 py-1 text-xs text-zinc-700">
                        置信 {Math.round(prediction.confidence * 100)}%
                      </div>
                    </div>
                    <div className="mt-2 text-sm text-zinc-600">
                      当前最高概率：{topOutcome.label} {Math.round(topOutcome.value * 100)}%
                    </div>
                    {tags.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {tags.map((tag) => (
                          <StatusBadge key={tag.label} tone={tag.tone}>
                            {tag.label}
                          </StatusBadge>
                        ))}
                      </div>
                    ) : null}
                    <div className="mt-2 text-xs text-zinc-500 line-clamp-2">
                      {(prediction.factors || []).slice(0, 2).join("；") || "暂无关键因素说明"}
                    </div>
                    <div className="mt-3">
                      <Link href={`/fixtures/${prediction.fixture_id}?date=${activeSalesDay}`} className="text-xs font-medium text-zinc-700 hover:text-zinc-950">
                        进入单场详情
                      </Link>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </SurfaceCard>

        <div className="grid gap-6">
          <SurfaceCard title="系统状态与刷新口径">
            <div className="grid gap-3">
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm">
                <div className="font-medium text-zinc-950">环境、数据库与销售日口径</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <StatusBadge tone={coreEnvOk ? "success" : "danger"}>{coreEnvOk ? "核心环境 2/2" : "核心环境未就绪"}</StatusBadge>
                  <StatusBadge tone={optionalReadyCount === 3 ? "success" : "warning"}>可选能力 {optionalReadyCount}/3</StatusBadge>
                  <StatusBadge tone={systemStatus?.supabase.ok ? "success" : systemStatus?.supabase.ok === false ? "danger" : "neutral"}>
                    {systemStatus?.supabase.ok ? "数据库正常" : systemStatus?.supabase.ok === false ? "数据库异常" : "数据库待检测"}
                  </StatusBadge>
                  <StatusBadge tone="neutral">销售日 {activeSalesDay}</StatusBadge>
                </div>
                <div className="mt-2 text-xs text-zinc-500">
                  {systemStatus?.supabase.error || dashboard?.sales_window.message || "建议先确认环境、数据库和当前销售日数据同步状态，再处理重点比赛。"}
                </div>
                <div className="mt-2 text-xs text-zinc-500">
                  销售窗：{dashboard?.sales_window.window_start ? formatDateTime(dashboard.sales_window.window_start) : "—"} 至{" "}
                  {dashboard?.sales_window.window_end ? formatDateTime(dashboard.sales_window.window_end) : "—"}
                </div>
                {coreMissingEnvItems.length > 0 ? <div className="mt-2 text-xs text-red-700">核心缺失：{coreMissingEnvItems.join("、")}</div> : null}
                {optionalMissingEnvItems.length > 0 ? <div className="mt-2 text-xs text-amber-700">可选未配：{optionalMissingEnvItems.join("、")}</div> : null}
              </div>
              <Link href="/setup" className="rounded-xl border border-zinc-200 px-4 py-3 text-sm hover:bg-zinc-50">
                去系统页检查环境变量、数据库和导入状态
              </Link>
              <Link href="/review" className="rounded-xl border border-zinc-200 px-4 py-3 text-sm hover:bg-zinc-50">
                去复盘页查看历史结果与盈亏
              </Link>
            </div>
          </SurfaceCard>

          <SurfaceCard title="今日待处理事项" description="把当前销售日还没处理完的比赛和系统项集中到一处。">
            <div className="grid gap-3">
              <div className="rounded-xl border border-zinc-200 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-zinc-950">待补预测比赛</div>
                  <StatusBadge tone={missingPredictionCount > 0 ? "warning" : "success"}>
                    {missingPredictionCount > 0 ? `${missingPredictionCount} 场待补` : "已覆盖"}
                  </StatusBadge>
                </div>
                <div className="mt-2 text-xs text-zinc-500">
                  {missingPredictionFixtures.length > 0
                    ? missingPredictionFixtures
                        .map(
                          (fixture) =>
                            `${fixture.home_team_name_zh || teamNameZh(fixture.home_team_name)} vs ${
                              fixture.away_team_name_zh || teamNameZh(fixture.away_team_name)
                            }`,
                        )
                        .join("；")
                    : "当前首页已拿到的比赛都存在预测结果。"}
                </div>
                <Link href={`/fixtures?date=${activeSalesDay}`} className="mt-3 inline-block text-xs font-medium text-zinc-700 hover:text-zinc-950">
                  去比赛页核对赛程与导入
                </Link>
              </div>

              <div className="rounded-xl border border-zinc-200 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-zinc-950">重点信号待查看</div>
                  <StatusBadge tone={signalNeedsReview.length > 0 ? "danger" : "success"}>
                    {signalNeedsReview.length > 0 ? `${signalNeedsReview.length} 场优先处理` : "已查看主链路"}
                  </StatusBadge>
                </div>
                <div className="mt-2 text-xs text-zinc-500">
                  {signalNeedsReview.length > 0
                    ? signalNeedsReview
                        .map(
                          (item) =>
                            `${item.fixture.home_team_name_zh || teamNameZh(item.fixture.home_team_name)} vs ${
                              item.fixture.away_team_name_zh || teamNameZh(item.fixture.away_team_name)
                            }`,
                        )
                        .join("；")
                    : "当前首页列出的重点比赛基本都已经进入预测链路。"}
                </div>
                <Link href={`/fixtures?date=${activeSalesDay}`} className="mt-3 inline-block text-xs font-medium text-zinc-700 hover:text-zinc-950">
                  去比赛页查看重点信号
                </Link>
              </div>

              <div className="rounded-xl border border-zinc-200 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-zinc-950">系统待处理项</div>
                  <StatusBadge tone={coreMissingEnvItems.length > 0 || systemStatus?.supabase.ok === false ? "warning" : "success"}>
                    {coreMissingEnvItems.length > 0 || systemStatus?.supabase.ok === false ? "需要检查" : "状态正常"}
                  </StatusBadge>
                </div>
                <div className="mt-2 text-xs text-zinc-500">
                  {coreMissingEnvItems.length > 0
                    ? `核心环境待补：${coreMissingEnvItems.join("、")}`
                    : systemStatus?.supabase.ok === false
                      ? systemStatus?.supabase.error || "数据库连接异常"
                      : optionalMissingEnvItems.length > 0
                        ? `可选能力未配置（不影响主流程）：${optionalMissingEnvItems.join("、")}`
                        : dashboard?.registry.next_task_key
                          ? `下一个任务：${dashboard?.registry.next_task_key}`
                          : "环境变量和数据库状态当前没有明显阻塞项。"}
                </div>
                <Link href="/setup" className="mt-3 inline-block text-xs font-medium text-zinc-700 hover:text-zinc-950">
                  去系统页处理
                </Link>
              </div>
            </div>
          </SurfaceCard>
        </div>
      </section>
    </div>
  );
}
