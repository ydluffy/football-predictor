"use client";

import { useEffect, useMemo, useState } from "react";
import { getReviewLedger, type ReviewLedgerDay, type ReviewLedgerMonth, getReviews, type ReviewPlanItem, type ReviewSummary } from "@/lib/api";
import { ActionButton, Chip, EmptyState, PageIntro, PrimaryLink, SecondaryLink, StatStrip, StatusBadge, SurfaceCard } from "@/components/Workbench";

function formatMoney(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}
function formatPercent(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function toneByProfit(value: number) {
  if (value > 0) return "success" as const;
  if (value < 0) return "danger" as const;
  return "neutral" as const;
}

function toneByResult(result: string) {
  if (/命中|hit/i.test(result)) return "success" as const;
  if (/未中|miss/i.test(result)) return "danger" as const;
  return "neutral" as const;
}

// 台账/月度共用的行内指标，替代原先 5~6 个嵌套色块。
function InlineStats({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
      {items.map((item) => (
        <span key={item.label}>
          {item.label} <span className="tabular-nums text-zinc-900">{item.value}</span>
        </span>
      ))}
    </div>
  );
}

const TH = "whitespace-nowrap px-3 py-2 text-xs font-medium";
const TD = "whitespace-nowrap px-3 py-2.5 text-xs";

export default function ReviewPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<ReviewSummary[]>([]);
  const [plans, setPlans] = useState<ReviewPlanItem[]>([]);
  const [days, setDays] = useState<ReviewLedgerDay[]>([]);
  const [months, setMonths] = useState<ReviewLedgerMonth[]>([]);
  const [selectedDay, setSelectedDay] = useState("all");

  useEffect(() => {
    let mounted = true;
    async function load() {
      setBusy(true);
      setError(null);
      try {
        const [ledger, data] = await Promise.all([getReviewLedger(), getReviews()]);
        if (!mounted) return;
        setDays(ledger.days || []);
        setMonths(ledger.months || []);
        setSummaries(data.summaries || []);
        setPlans(data.plans || []);
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted) setBusy(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, []);

  const availableDays = useMemo(() => ["all", ...summaries.map((item) => item.sales_day)], [summaries]);
  const filteredSummaries = useMemo(
    () => (selectedDay === "all" ? summaries : summaries.filter((item) => item.sales_day === selectedDay)),
    [selectedDay, summaries],
  );
  const filteredPlans = useMemo(
    () => (selectedDay === "all" ? plans : plans.filter((item) => item.sales_day === selectedDay)),
    [plans, selectedDay],
  );
  const filteredDays = useMemo(
    () => (selectedDay === "all" ? days : days.filter((item) => item.summary.sales_day === selectedDay)),
    [days, selectedDay],
  );

  const totalStake = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.stake, 0), [filteredSummaries]);
  const totalProfit = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.net_profit, 0), [filteredSummaries]);
  const totalHits = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.hits, 0), [filteredSummaries]);
  const totalPlans = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.plans, 0), [filteredSummaries]);

  // 当前连红：从最近销售日往前数，连续 net_profit > 0 的天数
  const currentStreak = useMemo(() => {
    let streak = 0;
    for (const item of summaries) {
      if (item.net_profit > 0) streak += 1;
      else break;
    }
    return streak;
  }, [summaries]);

  // 近 10 个方案的命中数（方案口径，比天级更细）
  const recentPlanRecord = useMemo(() => {
    const recent = plans.slice(0, 10);
    const hits = recent.filter((item) => /命中|hit/i.test(item.result)).length;
    return { total: recent.length, hits };
  }, [plans]);

  // 滚动 30 天（以最新销售日为锚）
  const rolling30 = useMemo(() => {
    if (summaries.length === 0) return null;
    const anchor = new Date(`${summaries[0].sales_day}T12:00:00+08:00`).getTime();
    const cutoff = anchor - 30 * 24 * 3600 * 1000;
    const window = summaries.filter((item) => new Date(`${item.sales_day}T12:00:00+08:00`).getTime() >= cutoff);
    const stake = window.reduce((sum, item) => sum + item.stake, 0);
    const profit = window.reduce((sum, item) => sum + item.net_profit, 0);
    return { days: window.length, stake, profit, roi: stake > 0 ? profit / stake : null };
  }, [summaries]);

  // 近 7 天命中方案数
  const last7DaysHits = useMemo(() => {
    if (summaries.length === 0) return 0;
    const anchor = new Date(`${summaries[0].sales_day}T12:00:00+08:00`).getTime();
    const cutoff = anchor - 7 * 24 * 3600 * 1000;
    return summaries
      .filter((item) => new Date(`${item.sales_day}T12:00:00+08:00`).getTime() >= cutoff)
      .reduce((sum, item) => sum + item.hits, 0);
  }, [summaries]);

  const rolling30Roi = rolling30 && rolling30.roi != null ? rolling30.roi : null;

  const visibleMonths = useMemo(() => {
    if (selectedDay !== "all") {
      const month = selectedDay.slice(0, 7);
      return months.filter((item) => item.month === month);
    }
    return months;
  }, [months, selectedDay]);

  return (
    <div className="grid gap-5">
      <PageIntro
        eyebrow="复盘"
        title="战绩"
        description="连红、近 X 中 Y、滚动 30 天盈利率为头部口径，往下是销售日台账、月度表现与逐方案明细。"
        actions={
          <>
            <PrimaryLink href="/fixtures">回到比赛</PrimaryLink>
            <SecondaryLink href="/predictions">查看预测</SecondaryLink>
          </>
        }
      />

      <StatStrip
        items={[
          { label: "复盘销售日", value: busy ? "…" : String(filteredSummaries.length) },
          { label: "方案总数", value: busy ? "…" : String(totalPlans), hint: `命中 ${totalHits}` },
          { label: "累计投入", value: busy ? "…" : `${totalStake.toFixed(2)} 元` },
          {
            label: "累计盈亏",
            value: busy ? "…" : formatMoney(totalProfit),
            tone: totalProfit > 0 ? "success" : totalProfit < 0 ? "danger" : "neutral",
          },
        ]}
      />

      <StatStrip
        items={[
          {
            label: "当前连红",
            value: busy ? "…" : `${currentStreak} 天`,
            hint: "连续盈利的销售日数",
            tone: currentStreak > 0 ? "success" : "neutral",
          },
          {
            label: "近期方案",
            value: busy ? "…" : recentPlanRecord.total > 0 ? `近 ${recentPlanRecord.total} 中 ${recentPlanRecord.hits}` : "—",
            hint: "最近 10 个方案",
          },
          {
            label: "滚动 30 天盈利率",
            value: busy ? "…" : formatPercent(rolling30Roi),
            hint: rolling30 ? `覆盖 ${rolling30.days} 天 · 盈亏 ${formatMoney(rolling30.profit)}` : "暂无数据",
            tone: rolling30Roi != null ? toneByProfit(rolling30Roi) : "neutral",
          },
          { label: "近 7 天命中", value: busy ? "…" : String(last7DaysHits), hint: "已结算命中方案数" },
        ]}
      />

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">复盘数据加载失败：{error}</div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-zinc-500">销售日</span>
        {availableDays.map((day) => (
          <Chip key={day} active={selectedDay === day} onClick={() => setSelectedDay(day)}>
            {day === "all" ? "全部" : day}
          </Chip>
        ))}
      </div>

      <SurfaceCard
        title="销售日台账"
        action={
          <ActionButton tone="secondary" onClick={() => setSelectedDay("all")} disabled={selectedDay === "all"}>
            查看全部
          </ActionButton>
        }
      >
        {filteredDays.length === 0 ? (
          <EmptyState text="当前还没有已入库的销售日复盘台账。" />
        ) : (
          <div>
            {filteredDays.map((day) => (
              <article key={day.summary.sales_day} className="border-b border-zinc-100 py-3 first:pt-0 last:border-b-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium tabular-nums text-zinc-900">{day.summary.sales_day}</span>
                    <StatusBadge tone={toneByProfit(day.summary.net_profit)}>盈亏 {formatMoney(day.summary.net_profit)}</StatusBadge>
                    <StatusBadge tone={day.summary.hits > day.summary.misses ? "success" : "warning"}>
                      命中 {day.summary.hits}/{day.summary.plans}
                    </StatusBadge>
                    <span className="text-xs text-zinc-400">
                      {day.summary.reviewed_at?.slice(0, 16).replace("T", " ") || "—"}
                    </span>
                  </div>
                  <InlineStats
                    items={[
                      { label: "方案", value: String(day.summary.plans) },
                      { label: "命中/未中", value: `${day.summary.hits} / ${day.summary.misses}` },
                      { label: "投入", value: `${day.summary.stake.toFixed(2)} 元` },
                      { label: "返还", value: `${day.summary.payout.toFixed(2)} 元` },
                      { label: "ROI", value: formatPercent(day.summary.roi) },
                    ]}
                  />
                </div>
                {day.plans.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {day.plans.slice(0, 6).map((plan) => (
                      <StatusBadge key={`${plan.sales_day}-${plan.plan_id}`} tone={toneByResult(plan.result)}>
                        {plan.plan_id}
                      </StatusBadge>
                    ))}
                    {day.plans.length > 6 ? <StatusBadge tone="neutral">其余 {day.plans.length - 6} 个</StatusBadge> : null}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard title="月度表现">
        {visibleMonths.length === 0 ? (
          <EmptyState text="当前还没有可用的月度复盘汇总。" />
        ) : (
          <div>
            {visibleMonths.map((month) => (
              <article key={month.month} className="border-b border-zinc-100 py-3 first:pt-0 last:border-b-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium tabular-nums text-zinc-900">{month.month}</span>
                    <StatusBadge tone={toneByProfit(month.net_profit)}>盈亏 {formatMoney(month.net_profit)}</StatusBadge>
                  </div>
                  <InlineStats
                    items={[
                      { label: "销售日", value: String(month.sales_day_count) },
                      { label: "方案", value: String(month.plan_count) },
                      { label: "命中/未中", value: `${month.hit_count} / ${month.miss_count}` },
                      { label: "投入", value: `${month.stake.toFixed(2)} 元` },
                      { label: "返还", value: `${month.payout.toFixed(2)} 元` },
                      { label: "ROI", value: formatPercent(month.roi) },
                    ]}
                  />
                </div>
              </article>
            ))}
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard title="往期预测摘要">
        {filteredSummaries.length === 0 ? (
          <EmptyState text="当前还没有可展示的往期预测摘要。" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead className="border-b border-zinc-200 bg-zinc-50">
                <tr className="text-zinc-500">
                  <th className={`${TH} text-left`}>销售日</th>
                  <th className={`${TH} text-left`}>状态</th>
                  <th className={`${TH} text-right`}>方案数</th>
                  <th className={`${TH} text-right`}>命中/未中</th>
                  <th className={`${TH} text-right`}>投入</th>
                  <th className={`${TH} text-right`}>返还</th>
                  <th className={`${TH} text-right`}>盈亏</th>
                  <th className={`${TH} text-right`}>ROI</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {filteredSummaries.map((item) => (
                  <tr key={item.sales_day}>
                    <td className={`${TD} text-zinc-900`}>
                      <div className="tabular-nums font-medium">{item.sales_day}</div>
                      <div className="mt-0.5 text-zinc-400">
                        {item.reviewed_at?.slice(0, 16).replace("T", " ") || "—"}
                      </div>
                    </td>
                    <td className={TD}>
                      <StatusBadge tone="neutral">{item.status}</StatusBadge>
                    </td>
                    <td className={`${TD} text-right tabular-nums text-zinc-700`}>{item.plans}</td>
                    <td className={`${TD} text-right tabular-nums text-zinc-700`}>
                      {item.hits}/{item.misses}
                    </td>
                    <td className={`${TD} text-right tabular-nums text-zinc-700`}>{item.stake.toFixed(2)}</td>
                    <td className={`${TD} text-right tabular-nums text-zinc-700`}>{item.payout.toFixed(2)}</td>
                    <td className={`${TD} text-right tabular-nums font-medium`}>
                      <span className={item.net_profit > 0 ? "text-emerald-700" : item.net_profit < 0 ? "text-red-600" : "text-zinc-700"}>
                        {formatMoney(item.net_profit)}
                      </span>
                    </td>
                    <td className={`${TD} text-right tabular-nums text-zinc-700`}>{formatPercent(item.roi)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard title="推荐方案复盘" action={<span className="text-xs text-zinc-400">{filteredPlans.length} 个方案</span>}>
        {filteredPlans.length === 0 ? (
          <EmptyState text="当前日期没有可展示的方案复盘记录。" />
        ) : (
          <div>
            {filteredPlans.map((plan) => (
              <article key={`${plan.sales_day}-${plan.plan_id}`} className="border-b border-zinc-100 py-3 first:pt-0 last:border-b-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-zinc-900">{plan.plan_id}</span>
                    <StatusBadge tone={toneByResult(plan.result)}>{plan.result}</StatusBadge>
                    <span className="text-xs text-zinc-400">
                      {plan.sales_day} · {plan.category}
                    </span>
                  </div>
                  <InlineStats
                    items={[
                      { label: "投入", value: `${plan.stake.toFixed(2)} 元` },
                      { label: "返还", value: `${plan.payout.toFixed(2)} 元` },
                      { label: "ROI", value: formatPercent(plan.roi) },
                    ]}
                  />
                </div>
                {plan.note ? <p className="mt-1.5 text-xs leading-5 text-zinc-500">{plan.note}</p> : null}
              </article>
            ))}
          </div>
        )}
      </SurfaceCard>
    </div>
  );
}
