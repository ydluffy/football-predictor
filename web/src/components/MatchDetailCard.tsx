"use client";

import type { Fixture, FixtureMarketIntel, Prediction } from "@/lib/api";
import { competitionNameZh, formatLocalTimeFromUtc, statusZh, teamNameZh } from "@/lib/zh";
import { ProbBar } from "@/components/ProbBar";
import { StatusBadge } from "@/components/Workbench";
import { evaluateSportteryHandicap } from "@/lib/handicap";

function pct(value?: number | null) {
  return value == null ? "-" : `${Math.round(value * 100)}%`;
}

function signed(value?: number | null, digits = 2, suffix = "") {
  if (value == null) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}${suffix}`;
}

function formatTimelineTime(value?: string | null) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function MatchDetailCard({
  fixture,
  prediction,
  marketIntel,
  actions,
}: {
  fixture: Fixture;
  prediction?: Prediction | null;
  marketIntel?: FixtureMarketIntel | null;
  actions?: React.ReactNode;
}) {
  const hasScore = fixture.home_score != null && fixture.away_score != null;
  const statusText = fixture.status_zh || statusZh(fixture.status);
  const topOutcome = prediction
    ? [
        { label: "主胜", value: prediction.p_home },
        { label: "平", value: prediction.p_draw },
        { label: "客胜", value: prediction.p_away },
      ].sort((a, b) => b.value - a.value)[0]
    : null;
  const handicapValue = marketIntel?.alignment?.sporttery_handicap ?? prediction?.sporttery_handicap ?? null;
  const handicapEvaluation = evaluateSportteryHandicap(prediction, handicapValue);

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs text-zinc-500">
            {fixture.competition_name_zh || competitionNameZh(fixture.competition_code, fixture.competition_name)}
            {fixture.competition_code ? <span className="ml-2 text-zinc-400">{fixture.competition_code}</span> : null}
            <span className="ml-2 text-zinc-400">#{fixture.fixture_id}</span>
          </div>
          <div className="mt-1 text-xl font-semibold text-zinc-950">
            {fixture.home_team_name_zh || teamNameZh(fixture.home_team_name)} vs{" "}
            {fixture.away_team_name_zh || teamNameZh(fixture.away_team_name)}
          </div>
          <div className="mt-2 text-sm text-zinc-500">
            北京时间 {fixture.kickoff_time_zh || formatLocalTimeFromUtc(fixture.utc_date, "Asia/Shanghai")}
            <span className="ml-2 text-zinc-400">UTC {fixture.utc_date?.slice(11, 16) || "-"}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={hasScore ? "success" : "neutral"}>
            {hasScore ? `${fixture.home_score}-${fixture.away_score}` : "比分待更新"}
          </StatusBadge>
          <StatusBadge
            tone={
              hasScore ? "success" : ["IN_PLAY", "LIVE", "PAUSED"].includes((fixture.status || "").toUpperCase()) ? "warning" : "neutral"
            }
          >
            {statusText || "待开赛"}
          </StatusBadge>
          {prediction ? (
            <StatusBadge tone={prediction.confidence >= 0.65 ? "success" : "warning"}>
              置信 {Math.round(prediction.confidence * 100)}%
            </StatusBadge>
          ) : null}
        </div>
      </div>

      {actions ? <div className="mt-4 flex flex-wrap gap-2">{actions}</div> : null}

      {prediction ? (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_0.95fr]">
          <div className="grid gap-3">
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
              <div className="text-sm font-semibold text-zinc-900">胜平负概率</div>
              <div className="mt-3 grid gap-2">
                <ProbBar label="主胜" value={prediction.p_home} />
                <ProbBar label="平" value={prediction.p_draw} />
                <ProbBar label="客胜" value={prediction.p_away} />
              </div>
            </div>

            <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700">
              <div className="font-semibold text-zinc-900">关键判断</div>
              <div className="mt-2">
                当前最高概率为 {topOutcome?.label || "-"}，约 {topOutcome ? Math.round(topOutcome.value * 100) : "-"}%。
              </div>
              {handicapEvaluation ? (
                <>
                  <div className="mt-2">{handicapEvaluation.summary}。</div>
                  <div className="mt-2">
                    让胜 {Math.round(handicapEvaluation.p_let_win * 100)}%，让平 {Math.round(handicapEvaluation.p_let_draw * 100)}%，让负{" "}
                    {Math.round(handicapEvaluation.p_let_lose * 100)}%。
                  </div>
                </>
              ) : null}
              <div className="mt-2">
                期望进球：主队 {prediction.lambda_home.toFixed(2)}，客队 {prediction.lambda_away.toFixed(2)}。
              </div>
              <div className="mt-2">
                Top 比分：
                {prediction.scorelines_top?.length
                  ? prediction.scorelines_top
                      .slice(0, 3)
                      .map((s) => `${s.home_goals}-${s.away_goals}(${Math.round(s.p * 100)}%)`)
                      .join("，")
                  : "暂无"}
              </div>
              <div className="mt-2">
                大 2.5：{pct(prediction.p_over_2_5)}，小 2.5：{pct(prediction.p_under_2_5)}，双方进球：{pct(prediction.p_btts_yes)}
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className="rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-700">
              <div className="font-semibold text-zinc-900">模型说明</div>
              <ul className="mt-2 list-disc pl-5">
                {prediction.factors.slice(0, 4).map((factor, index) => (
                  <li key={index} className="leading-6">
                    {factor}
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
              <div className="font-semibold">价值投注建议</div>
              <div className="mt-2">{prediction.betting_recommendation || "当前未提供赔率或 EV/Kelly 信息。"}</div>
            </div>

            {marketIntel?.movement || marketIntel?.alignment ? <MarketIntelPanel marketIntel={marketIntel} /> : null}
          </div>
        </div>
      ) : (
        <div className="mt-5 grid gap-3">
          <div className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50 px-4 py-5 text-sm text-zinc-500">
            这场比赛当前还没有对应预测结果。你可以先去预测页刷新，或先确认当天赛程是否已完成导入。
          </div>
          {marketIntel?.movement || marketIntel?.alignment ? <MarketIntelPanel marketIntel={marketIntel} /> : null}
        </div>
      )}
    </section>
  );
}

function MarketIntelPanel({ marketIntel }: { marketIntel: FixtureMarketIntel }) {
  const timelineItems = [
    marketIntel.movement
      ? {
          title: "外盘初盘",
          time: formatTimelineTime(marketIntel.movement.opening_captured_at),
          body: `主队让球中位 ${signed(marketIntel.movement.opening_home_handicap_median)}`,
        }
      : null,
    marketIntel.movement
      ? {
          title: "外盘最新盘",
          time: formatTimelineTime(marketIntel.movement.latest_captured_at),
          body: `主队让球中位 ${signed(marketIntel.movement.latest_home_handicap_median)}，强度变化 ${signed(
            marketIntel.movement.home_line_strength_delta,
            2,
            " 球",
          )}`,
        }
      : null,
    marketIntel.alignment
      ? {
          title: "体彩对齐快照",
          time: formatTimelineTime(marketIntel.alignment.sporttery_captured_at),
          body: `体彩 ${signed(marketIntel.alignment.sporttery_handicap, 0)} / 外盘中位 ${signed(
            marketIntel.alignment.outer_home_handicap_median,
          )}，差值 ${signed(marketIntel.alignment.sporttery_minus_outer_handicap_median)}`,
        }
      : null,
  ].filter(Boolean) as Array<{ title: string; time: string; body: string }>;

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <div className="font-semibold">盘口观察</div>
      {timelineItems.length > 0 ? (
        <div className="mt-3 grid gap-0">
          {timelineItems.map((item, index) => (
            <div key={`${item.title}-${index}`} className="grid grid-cols-[18px_1fr] gap-3">
              <div className="flex flex-col items-center">
                <div className="mt-1 h-2.5 w-2.5 rounded-full bg-amber-600" />
                {index < timelineItems.length - 1 ? <div className="mt-1 w-px flex-1 bg-amber-300" /> : null}
              </div>
              <div className={index < timelineItems.length - 1 ? "pb-4" : ""}>
                <div className="text-xs font-medium text-amber-900">{item.title}</div>
                <div className="mt-0.5 text-[11px] text-amber-700">{item.time}</div>
                <div className="mt-1 text-xs leading-6">{item.body}</div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {marketIntel.movement ? (
        <div className="mt-3 grid gap-1 text-xs leading-6">
          <div>
            水位概率变化：
            {signed((marketIntel.movement.home_price_probability_delta ?? 0) * 100, 1, "pp")}
          </div>
          <div>
            快照 / 机构：{marketIntel.movement.snapshot_count} / {marketIntel.movement.bookmaker_count}
          </div>
          <div>
            信号：{marketIntel.movement.line_upgrade_without_price_support ? "升盘但价格未同步支持" : "无明显升盘背离"}
            {marketIntel.movement.line_downgrade ? "；存在退盘" : ""}
          </div>
        </div>
      ) : null}
      {marketIntel.alignment ? (
        <div className="mt-3 grid gap-1 text-xs leading-6">
          <div>
            对齐机构：{marketIntel.alignment.aligned_bookmaker_count}，外盘对齐时间：
            {formatTimelineTime(marketIntel.alignment.outer_captured_at)}
          </div>
          <div>
            时间对齐：{marketIntel.alignment.time_aligned ? "已满足" : "未满足"}，最小时间差：
            {marketIntel.alignment.min_time_delta_minutes != null
              ? `${Math.round(marketIntel.alignment.min_time_delta_minutes)} 分钟`
              : "-"}
          </div>
        </div>
      ) : null}
    </div>
  );
}
