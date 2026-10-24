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

// 小节标题：只做分组，不做视觉重量。
function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-xs font-medium text-zinc-500">{children}</div>;
}

function StatGrid({ items }: { items: Array<{ label: string; value: string; hint?: string }> }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-3">
      {items.map((item) => (
        <div key={item.label}>
          <div className="text-xs text-zinc-500">{item.label}</div>
          <div className="mt-0.5 text-xs font-medium tabular-nums text-zinc-900">{item.value}</div>
          {item.hint ? <div className="mt-0.5 text-xs tabular-nums text-zinc-400">{item.hint}</div> : null}
        </div>
      ))}
    </div>
  );
}

/**
 * 单场详情内容块。本身不带边框与卡片，
 * 由调用方决定放在 SurfaceCard 里（预测页 / 详情页）还是裸用（比赛页）。
 */
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

  const keyStats = prediction
    ? [
        {
          label: "让球",
          value: handicapEvaluation ? `${handicapEvaluation.compactText} ${handicapEvaluation.topLabel}` : "—",
          hint: handicapEvaluation
            ? `让胜 ${pct(handicapEvaluation.p_let_win)} / 让平 ${pct(handicapEvaluation.p_let_draw)} / 让负 ${pct(
                handicapEvaluation.p_let_lose,
              )}`
            : undefined,
        },
        {
          label: "期望进球 λ",
          value: `${prediction.lambda_home.toFixed(2)} / ${prediction.lambda_away.toFixed(2)}`,
          hint: "主队 / 客队",
        },
        {
          label: "Top 比分",
          value: prediction.scorelines_top?.length
            ? prediction.scorelines_top
                .slice(0, 3)
                .map((s) => `${s.home_goals}-${s.away_goals}(${Math.round(s.p * 100)}%)`)
                .join(" ")
            : "—",
        },
        { label: "大小球 2.5", value: `大 ${pct(prediction.p_over_2_5)} / 小 ${pct(prediction.p_under_2_5)}` },
        { label: "双方进球", value: pct(prediction.p_btts_yes) },
      ]
    : [];

  const hasIntel = Boolean(marketIntel?.movement || marketIntel?.alignment);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            <span>{fixture.competition_name_zh || competitionNameZh(fixture.competition_code, fixture.competition_name)}</span>
            {fixture.competition_code ? <span className="text-zinc-400">{fixture.competition_code}</span> : null}
            <span className="tabular-nums text-zinc-400">#{fixture.fixture_id}</span>
          </div>
          <div className="mt-1 text-base font-semibold text-zinc-900">
            {fixture.home_team_name_zh || teamNameZh(fixture.home_team_name)} vs{" "}
            {fixture.away_team_name_zh || teamNameZh(fixture.away_team_name)}
          </div>
          <div className="mt-0.5 text-xs text-zinc-500">
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

      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}

      {prediction ? (
        <>
          <div className="grid gap-4 border-t border-zinc-100 pt-4 lg:grid-cols-2">
            <div>
              <SectionLabel>胜平负概率</SectionLabel>
              <div className="mt-2 grid gap-2">
                <ProbBar label="主胜" value={prediction.p_home} />
                <ProbBar label="平" value={prediction.p_draw} />
                <ProbBar label="客胜" value={prediction.p_away} />
              </div>
            </div>
            <div>
              <SectionLabel>关键判断</SectionLabel>
              <p className="mt-2 text-xs leading-5 text-zinc-700">
                当前最高概率为 {topOutcome?.label || "-"}
                {topOutcome ? `，约 ${Math.round(topOutcome.value * 100)}%` : ""}。
                {handicapEvaluation ? ` ${handicapEvaluation.summary}。` : ""}
              </p>
            </div>
          </div>

          <div className="border-t border-zinc-100 pt-4">
            <SectionLabel>衍生指标</SectionLabel>
            <div className="mt-2">
              <StatGrid items={keyStats} />
            </div>
          </div>

          <div className="grid gap-4 border-t border-zinc-100 pt-4 lg:grid-cols-2">
            <div>
              <SectionLabel>模型说明</SectionLabel>
              {prediction.factors.length > 0 ? (
                <ul className="mt-2 list-disc pl-4 text-xs leading-5 text-zinc-600">
                  {prediction.factors.slice(0, 4).map((factor, index) => (
                    <li key={index}>{factor}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-zinc-400">暂无模型说明。</p>
              )}
            </div>
            <div>
              <SectionLabel>价值投注建议</SectionLabel>
              <p className="mt-2 text-xs leading-5 text-zinc-700">
                {prediction.betting_recommendation || "当前未提供赔率或 EV / Kelly 信息。"}
              </p>
            </div>
          </div>
        </>
      ) : (
        <div className="border-t border-zinc-100 pt-4 text-xs text-zinc-500">
          这场比赛当前还没有对应预测结果。可以先到预测页刷新，或先确认当天赛程是否已完成导入。
        </div>
      )}

      {hasIntel ? <MarketIntelPanel marketIntel={marketIntel as FixtureMarketIntel} /> : null}
    </div>
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

  const intelStats = [
    marketIntel.movement
      ? {
          label: "水位概率变化",
          value: signed((marketIntel.movement.home_price_probability_delta ?? 0) * 100, 1, "pp"),
        }
      : null,
    marketIntel.movement
      ? {
          label: "快照 / 机构",
          value: `${marketIntel.movement.snapshot_count} / ${marketIntel.movement.bookmaker_count}`,
        }
      : null,
    marketIntel.movement
      ? {
          label: "信号",
          value:
            (marketIntel.movement.line_upgrade_without_price_support ? "升盘但价格未同步支持" : "无明显升盘背离") +
            (marketIntel.movement.line_downgrade ? "；存在退盘" : ""),
        }
      : null,
    marketIntel.alignment
      ? { label: "对齐机构数", value: String(marketIntel.alignment.aligned_bookmaker_count) }
      : null,
    marketIntel.alignment
      ? { label: "外盘对齐时间", value: formatTimelineTime(marketIntel.alignment.outer_captured_at) }
      : null,
    marketIntel.alignment
      ? {
          label: "时间对齐",
          value: `${marketIntel.alignment.time_aligned ? "已满足" : "未满足"}${
            marketIntel.alignment.min_time_delta_minutes != null
              ? ` · 最小差 ${Math.round(marketIntel.alignment.min_time_delta_minutes)} 分钟`
              : ""
          }`,
        }
      : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  return (
    <div className="border-t border-zinc-100 pt-4">
      <SectionLabel>盘口观察</SectionLabel>
      <div className="mt-2 grid gap-3 lg:grid-cols-2">
        <div>
          {timelineItems.length > 0 ? (
            <div className="grid gap-0">
              {timelineItems.map((item, index) => (
                <div key={`${item.title}-${index}`} className="grid grid-cols-[12px_1fr] gap-3">
                  <div className="flex flex-col items-center">
                    <div className="mt-1.5 h-2 w-2 rounded-full bg-amber-500" />
                    {index < timelineItems.length - 1 ? <div className="mt-1 w-px flex-1 bg-zinc-200" /> : null}
                  </div>
                  <div className={index < timelineItems.length - 1 ? "pb-4" : ""}>
                    <div className="text-xs font-medium text-zinc-900">{item.title}</div>
                    <div className="mt-0.5 text-xs tabular-nums text-zinc-400">{item.time}</div>
                    <div className="mt-1 text-xs leading-5 text-zinc-600">{item.body}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        {intelStats.length > 0 ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 self-start">
            {intelStats.map((item) => (
              <div key={item.label}>
                <div className="text-xs text-zinc-500">{item.label}</div>
                <div className="mt-0.5 text-xs font-medium tabular-nums text-zinc-900">{item.value}</div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
