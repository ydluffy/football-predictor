"use client";

import { useEffect, useMemo, useState } from "react";
import { getReviews, type ReviewPlanItem, type ReviewSummary } from "@/lib/api";
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
  const [selectedDay, setSelectedDay] = useState("all");

  useEffect(() => {
    let mounted = true;
    async function load() {
      setBusy(true);
      setError(null);
      try {
        const data = await getReviews();
        if (!mounted) return;
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

  const totalStake = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.stake, 0), [filteredSummaries]);
  const totalProfit = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.net_profit, 0), [filteredSummaries]);
  const totalHits = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.hits, 0), [filteredSummaries]);
  const totalPlans = useMemo(() => filteredSummaries.reduce((sum, item) => sum + item.plans, 0), [filteredSummaries]);

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="往期预测与复盘"
        title="保留历史预测结果，也保留方案复盘轨迹"
        description="这页对应体彩的赛果开奖和后验查看思路。上半部分看销售日复盘摘要，下半部分看每个方案的命中、盈亏和复盘备注。"
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
