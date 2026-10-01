"use client";

import { useEffect, useMemo, useState } from "react";
import { getReviewLedger, type ReviewLedgerDay, type ReviewLedgerMonth, getReviews, type ReviewPlanItem, type ReviewSummary } from "@/lib/api";
import { ActionButton, EmptyState, MetricCard, PageIntro, PrimaryLink, SecondaryLink, SurfaceCard, StatusBadge } from "@/components/Workbench";

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

  // —— 战绩语言（纯前端计算，参考行业通用的连红/近X中Y/滚动30天口径）——
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
  const visibleMonths = useMemo(() => {
    if (selectedDay !== "all") {
      const month = selectedDay.slice(0, 7);
      return months.filter((item) => item.month === month);
    }
    return months;
  }, [months, selectedDay]);

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="往期预测与复盘"
        title="战绩怎么样，一目了然"
        description="头部用行业通用的战绩语言（连红、近X中Y、滚动30天盈利率）快速判断状态，往下是销售日台账、月度表现和逐方案明细。全部指标由已入库复盘数据直接计算。"
        actions={
          <>
            <PrimaryLink href="/fixtures">回到比赛页</PrimaryLink>
            <SecondaryLink href="/predictions">查看今日预测</SecondaryLink>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="复盘销售日" value={busy ? "…" : String(filteredSummaries.length)} hint="已接入的历史销售日数量" />
        <MetricCard label="方案总数" value={busy ? "…" : String(totalPlans)} hint="真实方案与部分观察方案的已结算记录" />
        <MetricCard label="命中方案" value={busy ? "…" : String(totalHits)} hint="命中数会随筛选销售日变化" />
        <MetricCard label="累计盈亏" value={busy ? "…" : formatMoney(totalProfit)} hint={`累计投入 ${totalStake.toFixed(2)} 元`} />
      </section>

      {error ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">复盘数据加载失败：{error}</section>
      ) : null}

      <SurfaceCard
        title="战绩速览"
        description="连红按销售日盈亏连续为正计算；近X中Y按最近结算方案计算；滚动30天以最新销售日为锚。"
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-4">
            <div className="text-xs text-zinc-500">当前连红</div>
            <div className={`mt-1 text-2xl font-semibold ${currentStreak > 0 ? "text-red-600" : "text-zinc-950"}`}>
              {busy ? "…" : currentStreak > 0 ? `${currentStreak} 天` : "0 天"}
            </div>
            <div className="mt-1 text-xs text-zinc-500">连续盈利的销售日数</div>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-4">
            <div className="text-xs text-zinc-500">近期方案</div>
            <div className="mt-1 text-2xl font-semibold text-zinc-950">
              {busy ? "…" : recentPlanRecord.total > 0 ? `近${recentPlanRecord.total}中${recentPlanRecord.hits}` : "—"}
            </div>
            <div className="mt-1 text-xs text-zinc-500">按最近结算的方案口径统计</div>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-4">
            <div className="text-xs text-zinc-500">滚动30天盈利率</div>
            <div
              className={`mt-1 text-2xl font-semibold ${
                rolling30 && rolling30.roi != null ? (rolling30.roi > 0 ? "text-emerald-700" : "text-red-700") : "text-zinc-950"
              }`}
            >
              {busy ? "…" : rolling30 && rolling30.roi != null ? formatPercent(rolling30.roi) : "—"}
            </div>
            <div className="mt-1 text-xs text-zinc-500">
              {rolling30 ? `覆盖 ${rolling30.days} 个销售日 · 盈亏 ${formatMoney(rolling30.profit)}` : "暂无可用数据"}
            </div>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-4">
            <div className="text-xs text-zinc-500">近7天命中</div>
            <div className="mt-1 text-2xl font-semibold text-zinc-950">{busy ? "…" : String(last7DaysHits)}</div>
            <div className="mt-1 text-xs text-zinc-500">最近 7 个自然日内结算的命中方案数</div>
          </div>
        </div>
      </SurfaceCard>

      <SurfaceCard
        title="销售日筛选"
        description="先选一个销售日，再看那一天的预测结论和推荐方案复盘。"
        action={
          <ActionButton tone="secondary" onClick={() => setSelectedDay("all")} disabled={selectedDay === "all"}>
            查看全部
          </ActionButton>
        }
      >
        <div className="flex flex-wrap gap-2">
          {availableDays.map((day) => {
            const active = selectedDay === day;
            return (
              <button
                key={day}
                onClick={() => setSelectedDay(day)}
                className={
                  active
                    ? "rounded-full bg-zinc-900 px-3 py-2 text-xs font-medium text-white"
                    : "rounded-full border border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-700 hover:bg-zinc-50"
                }
              >
                {day === "all" ? "全部销售日" : day}
              </button>
            );
          })}
        </div>
      </SurfaceCard>

      <SurfaceCard title="销售日台账" description="先看每天整体表现，再决定是否下钻到具体方案。这里更接近你要的操盘复盘总表。">
        {filteredDays.length === 0 ? (
          <EmptyState text="当前还没有已入库的销售日复盘台账。" />
        ) : (
          <div className="grid gap-3">
            {filteredDays.map((day) => (
              <article key={day.summary.sales_day} className="rounded-2xl border border-zinc-200 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-zinc-500">销售日</div>
                    <div className="mt-1 text-xl font-semibold text-zinc-950">{day.summary.sales_day}</div>
                    <div className="mt-1 text-sm text-zinc-500">
                      复盘时间 {day.summary.reviewed_at?.slice(0, 16).replace("T", " ") || "—"}，状态 {day.summary.status}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge tone={day.summary.net_profit > 0 ? "success" : day.summary.net_profit < 0 ? "danger" : "neutral"}>
                      盈亏 {formatMoney(day.summary.net_profit)}
                    </StatusBadge>
                    <StatusBadge tone={day.summary.hits > day.summary.misses ? "success" : "warning"}>
                      命中 {day.summary.hits}/{day.summary.plans}
                    </StatusBadge>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-5 text-sm text-zinc-700">
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">方案数</div>
                    <div className="mt-1 font-semibold text-zinc-950">{day.summary.plans}</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">命中 / 未中</div>
                    <div className="mt-1 font-semibold text-zinc-950">
                      {day.summary.hits} / {day.summary.misses}
                    </div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">投入</div>
                    <div className="mt-1 font-semibold text-zinc-950">{day.summary.stake.toFixed(2)} 元</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">返还</div>
                    <div className="mt-1 font-semibold text-zinc-950">{day.summary.payout.toFixed(2)} 元</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">ROI</div>
                    <div className="mt-1 font-semibold text-zinc-950">{formatPercent(day.summary.roi)}</div>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {day.plans.slice(0, 4).map((plan) => (
                    <StatusBadge key={`${plan.sales_day}-${plan.plan_id}`} tone={toneByResult(plan.result)}>
                      {plan.plan_id}
                    </StatusBadge>
                  ))}
                  {day.plans.length > 4 ? <StatusBadge tone="neutral">其余 {day.plans.length - 4} 个方案</StatusBadge> : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard title="月度表现" description="先按月看整体收益和命中，再判断模型或流程是否需要调参。这里先用真实复盘结果做月度汇总。">
        {visibleMonths.length === 0 ? (
          <EmptyState text="当前还没有可用的月度复盘汇总。" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {visibleMonths.map((month) => (
              <article key={month.month} className="rounded-2xl border border-zinc-200 bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-zinc-500">月份</div>
                    <div className="mt-1 text-xl font-semibold text-zinc-950">{month.month}</div>
                  </div>
                  <StatusBadge tone={month.net_profit > 0 ? "success" : month.net_profit < 0 ? "danger" : "neutral"}>
                    盈亏 {formatMoney(month.net_profit)}
                  </StatusBadge>
                </div>
                <div className="mt-4 grid gap-3 text-sm text-zinc-700 md:grid-cols-2">
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">销售日</div>
                    <div className="mt-1 font-semibold text-zinc-950">{month.sales_day_count}</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">方案数</div>
                    <div className="mt-1 font-semibold text-zinc-950">{month.plan_count}</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">命中 / 未中</div>
                    <div className="mt-1 font-semibold text-zinc-950">
                      {month.hit_count} / {month.miss_count}
                    </div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">ROI</div>
                    <div className="mt-1 font-semibold text-zinc-950">{formatPercent(month.roi)}</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">投入</div>
                    <div className="mt-1 font-semibold text-zinc-950">{month.stake.toFixed(2)} 元</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">返还</div>
                    <div className="mt-1 font-semibold text-zinc-950">{month.payout.toFixed(2)} 元</div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard title="往期预测摘要" description="对应每个销售日的真实方案表现，后续可以继续补充联赛、命中率、模型版本等查询条件。">
        {filteredSummaries.length === 0 ? (
          <EmptyState text="当前还没有可展示的往期预测摘要。" />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-y-2 text-sm">
              <thead>
                <tr className="text-left text-xs text-zinc-500">
                  <th className="px-3 py-2">销售日</th>
                  <th className="px-3 py-2">复盘时间</th>
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2">方案数</th>
                  <th className="px-3 py-2">命中/未中</th>
                  <th className="px-3 py-2">投入</th>
                  <th className="px-3 py-2">返还</th>
                  <th className="px-3 py-2">盈亏</th>
                  <th className="px-3 py-2">ROI</th>
                </tr>
              </thead>
              <tbody>
                {filteredSummaries.map((item) => (
                  <tr key={item.sales_day} className="rounded-2xl bg-zinc-50 text-zinc-800">
                    <td className="rounded-l-2xl px-3 py-3 font-medium text-zinc-950">{item.sales_day}</td>
                    <td className="px-3 py-3">{item.reviewed_at?.slice(0, 16).replace("T", " ") || "—"}</td>
                    <td className="px-3 py-3">
                      <StatusBadge tone="neutral">{item.status}</StatusBadge>
                    </td>
                    <td className="px-3 py-3">{item.plans}</td>
                    <td className="px-3 py-3">
                      {item.hits}/{item.misses}
                    </td>
                    <td className="px-3 py-3">{item.stake.toFixed(2)}</td>
                    <td className="px-3 py-3">{item.payout.toFixed(2)}</td>
                    <td className="px-3 py-3">
                      <span className={item.net_profit > 0 ? "text-emerald-700" : item.net_profit < 0 ? "text-red-700" : "text-zinc-700"}>
                        {formatMoney(item.net_profit)}
                      </span>
                    </td>
                    <td className="rounded-r-2xl px-3 py-3">{formatPercent(item.roi)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SurfaceCard>

      <SurfaceCard title="推荐方案复盘" description="先保留真实方案和固定赔率观察方案，后续可以继续补充每场比赛明细、串关腿命中情况和完整复盘正文。">
        {filteredPlans.length === 0 ? (
          <EmptyState text="当前日期没有可展示的方案复盘记录。" />
        ) : (
          <div className="grid gap-3">
            {filteredPlans.map((plan) => (
              <article key={`${plan.sales_day}-${plan.plan_id}`} className="rounded-2xl border border-zinc-200 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs text-zinc-500">
                      {plan.sales_day} · {plan.category}
                    </div>
                    <div className="mt-1 text-base font-semibold text-zinc-950">{plan.plan_id}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge tone={toneByResult(plan.result)}>{plan.result}</StatusBadge>
                    <StatusBadge tone={toneByProfit(plan.net_profit)}>{formatMoney(plan.net_profit)}</StatusBadge>
                  </div>
                </div>
                <div className="mt-3 grid gap-3 text-sm text-zinc-700 md:grid-cols-4">
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">投入</div>
                    <div className="mt-1 font-semibold text-zinc-950">{plan.stake.toFixed(2)} 元</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">返还</div>
                    <div className="mt-1 font-semibold text-zinc-950">{plan.payout.toFixed(2)} 元</div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">盈亏</div>
                    <div className={`mt-1 font-semibold ${plan.net_profit > 0 ? "text-emerald-700" : plan.net_profit < 0 ? "text-red-700" : "text-zinc-950"}`}>
                      {formatMoney(plan.net_profit)} 元
                    </div>
                  </div>
                  <div className="rounded-xl bg-zinc-50 px-3 py-3">
                    <div className="text-xs text-zinc-500">ROI</div>
                    <div className="mt-1 font-semibold text-zinc-950">{formatPercent(plan.roi)}</div>
                  </div>
                </div>
                {plan.note ? <div className="mt-3 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-3 text-sm text-zinc-700">{plan.note}</div> : null}
              </article>
            ))}
          </div>
        )}
      </SurfaceCard>
    </div>
  );
}
