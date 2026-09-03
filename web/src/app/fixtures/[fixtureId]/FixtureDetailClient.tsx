"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { Fixture, FixtureInsightResponse, FixtureMarketIntel, Prediction } from "@/lib/api";
import type { FixtureExplanationItem } from "@/lib/api";
import {
  explainFixture,
  getFixtureById,
  getFixtureInsights,
  getMarketIntel,
  getPredictionsByFixtureIds,
  listFixtureExplanations,
  saveFixtureExplanation,
} from "@/lib/api";
import { MatchDetailCard } from "@/components/MatchDetailCard";
import { EmptyState, MetricCard, PageIntro, SecondaryLink, StatusBadge, SurfaceCard } from "@/components/Workbench";

type ExplainSnapshot = {
  id: string;
  created_at: string;
  mode: "brief" | "detailed";
  content: string;
};

function storageKey(fixtureId: number) {
  return `fixture_explain_snapshots:${fixtureId}`;
}

function loadSnapshots(fixtureId: number): ExplainSnapshot[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(storageKey(fixtureId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x) => x && typeof x === "object")
      .map((x) => x as ExplainSnapshot)
      .filter((x) => typeof x.id === "string" && typeof x.created_at === "string" && typeof x.content === "string");
  } catch {
    return [];
  }
}

function saveSnapshots(fixtureId: number, items: ExplainSnapshot[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(fixtureId), JSON.stringify(items.slice(0, 20)));
  } catch {
    // ignore
  }
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function shanghaiDateFromIso(iso?: string | null) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

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

export function FixtureDetailClient({
  fixtureId,
  initialDate,
}: {
  fixtureId: number;
  initialDate?: string;
}) {
  const [loading, setLoading] = useState(true);
  const [fixture, setFixture] = useState<Fixture | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [marketIntel, setMarketIntel] = useState<FixtureMarketIntel | null>(null);
  const [insights, setInsights] = useState<FixtureInsightResponse | null>(null);
  const [explainMode, setExplainMode] = useState<"brief" | "detailed">("brief");
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainContent, setExplainContent] = useState<string>("");
  const [explainError, setExplainError] = useState<string | null>(null);
  const [saved, setSaved] = useState<ExplainSnapshot[]>([]);
  const [cloudLoading, setCloudLoading] = useState(false);
  const [cloudError, setCloudError] = useState<string | null>(null);
  const [cloudSaved, setCloudSaved] = useState<FixtureExplanationItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSaved(loadSnapshots(fixtureId));
  }, [fixtureId]);

  useEffect(() => {
    let mounted = true;
    async function loadCloud() {
      setCloudLoading(true);
      setCloudError(null);
      try {
        const r = await listFixtureExplanations(fixtureId);
        if (!mounted) return;
        setCloudSaved(r.items || []);
      } catch (e) {
        if (!mounted) return;
        setCloudError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted) setCloudLoading(false);
      }
    }
    loadCloud();
    return () => {
      mounted = false;
    };
  }, [fixtureId]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const fixtureResp = await getFixtureById(fixtureId);
        if (!fixtureResp.fixture) {
          throw new Error("未找到这场比赛。");
        }
        const [predResp, intelResp] = await Promise.all([
          getPredictionsByFixtureIds([fixtureId]).catch(() => ({ count: 0, predictions: [] })),
          getMarketIntel([fixtureResp.fixture]).catch(() => ({ count: 0, items: [] })),
        ]);
        const detailInsights = await getFixtureInsights(fixtureId).catch(() => null);
        if (!mounted) return;
        setFixture(fixtureResp.fixture);
        setPrediction(predResp.predictions[0] || null);
        setMarketIntel(intelResp.items[0] || null);
        setInsights(detailInsights);
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
  }, [fixtureId]);

  const backDate = useMemo(() => initialDate || shanghaiDateFromIso(fixture?.utc_date) || "", [fixture?.utc_date, initialDate]);
  const marketTags = useMemo(() => getMarketSignalTags(marketIntel), [marketIntel]);
  const oddsSnapshot = insights?.odds_snapshot || null;
  const predictionSnapshot = insights?.prediction_snapshot || null;
  const backtestReview = insights?.backtest_review || null;

  async function runExplain() {
    setExplainLoading(true);
    setExplainError(null);
    try {
      const r = await explainFixture(fixtureId, explainMode);
      setExplainContent(r.content || "");
    } catch (e) {
      setExplainError(e instanceof Error ? e.message : String(e));
    } finally {
      setExplainLoading(false);
    }
  }

  async function copyExplain() {
    if (!explainContent) return;
    try {
      await navigator.clipboard.writeText(explainContent);
    } catch {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = explainContent;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  }

  function saveExplain() {
    if (!explainContent) return;
    const item: ExplainSnapshot = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      created_at: new Date().toISOString(),
      mode: explainMode,
      content: explainContent,
    };
    const next = [item, ...saved].slice(0, 20);
    setSaved(next);
    saveSnapshots(fixtureId, next);
  }

  function deleteSnapshot(id: string) {
    const next = saved.filter((x) => x.id !== id);
    setSaved(next);
    saveSnapshots(fixtureId, next);
  }

  async function saveExplainToCloud() {
    if (!explainContent) return;
    setCloudLoading(true);
    setCloudError(null);
    try {
      await saveFixtureExplanation(fixtureId, {
        mode: explainMode,
        content: explainContent,
        source: "fixture_detail",
        meta: { saved_from: "fixture_detail_page" },
      });
      const r = await listFixtureExplanations(fixtureId);
      setCloudSaved(r.items || []);
    } catch (e) {
      setCloudError(e instanceof Error ? e.message : String(e));
    } finally {
      setCloudLoading(false);
    }
  }

  return (
    <div className="grid gap-6">
      <PageIntro
        eyebrow="单场详情"
        title={
          fixture
            ? `${fixture.home_team_name_zh || fixture.home_team_name || "主队"} vs ${
                fixture.away_team_name_zh || fixture.away_team_name || "客队"
              }`
            : `比赛 #${fixtureId}`
        }
        description={
          fixture
            ? `${fixture.competition_name_zh || fixture.competition_name || "赛事"} · ${
                fixture.kickoff_time_zh || fixture.utc_date || "时间待定"
              }`
            : "集中查看单场比赛的赛程、预测、盘口观察与后续入口。"
        }
        actions={
          <>
            <SecondaryLink href={backDate ? `/fixtures?date=${backDate}` : "/fixtures"}>回到比赛页</SecondaryLink>
            <SecondaryLink href={backDate ? `/predictions?date=${backDate}` : "/predictions"}>回到预测页</SecondaryLink>
            <SecondaryLink href="/chat">让助手解释</SecondaryLink>
          </>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="比赛编号" value={String(fixtureId)} hint="当前单场详情的 fixture_id" />
        <MetricCard label="预测状态" value={loading ? "…" : prediction ? "已生成" : "未生成"} hint="是否已拿到单场预测结果" />
        <MetricCard label="市场信号" value={loading ? "…" : String(marketTags.length)} hint="盘口与内外盘观察标签数" />
        <MetricCard
          label="盘口对齐"
          value={loading ? "…" : marketIntel?.alignment?.time_aligned ? "已对齐" : "待确认"}
          hint="体彩与外盘快照的时间对齐状态"
        />
      </section>

      {error ? (
        <section className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</section>
      ) : null}

      {!loading && !fixture ? (
        <EmptyState text="没有找到这场比赛。可能是 fixture_id 不存在，或当前数据库尚未同步到这场比赛。" />
      ) : null}

      {fixture ? (
        <SurfaceCard
          title="比赛详情"
          description="这里汇总赛程、预测、价值建议与盘口时间线，便于直接做单场判断。"
        >
          <MatchDetailCard
            fixture={fixture}
            prediction={prediction}
            marketIntel={marketIntel}
            actions={
              <>
                <Link
                  href={backDate ? `/predictions?date=${backDate}&fixtureId=${fixture.fixture_id}` : `/predictions?fixtureId=${fixture.fixture_id}`}
                  className="rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white"
                >
                  在预测页定位这场比赛
                </Link>
                <Link
                  href={backDate ? `/fixtures?date=${backDate}&fixtureId=${fixture.fixture_id}` : `/fixtures?fixtureId=${fixture.fixture_id}`}
                  className="rounded-xl border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                >
                  在比赛页定位这场比赛
                </Link>
              </>
            }
          />
        </SurfaceCard>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-2">
        <SurfaceCard title="赔率与模型快照" description="把当前赔率、已存预测快照和 EV/Kelly 摘要放在一起。">
          <div className="grid gap-4">
            <div className="rounded-xl border border-zinc-200 px-4 py-3">
              <div className="text-sm font-semibold text-zinc-950">当前赔率快照</div>
              {oddsSnapshot ? (
                <div className="mt-2 grid grid-cols-3 gap-3 text-sm">
                  <div className="rounded-lg bg-zinc-50 px-3 py-2">
                    <div className="text-xs text-zinc-500">主胜</div>
                    <div className="mt-1 font-semibold text-zinc-950">{oddsSnapshot.odds_home ?? "-"}</div>
                  </div>
                  <div className="rounded-lg bg-zinc-50 px-3 py-2">
                    <div className="text-xs text-zinc-500">平</div>
                    <div className="mt-1 font-semibold text-zinc-950">{oddsSnapshot.odds_draw ?? "-"}</div>
                  </div>
                  <div className="rounded-lg bg-zinc-50 px-3 py-2">
                    <div className="text-xs text-zinc-500">客胜</div>
                    <div className="mt-1 font-semibold text-zinc-950">{oddsSnapshot.odds_away ?? "-"}</div>
                  </div>
                </div>
              ) : (
                <EmptyState text="当前没有可用的赔率快照。" />
              )}
            </div>

            <div className="rounded-xl border border-zinc-200 px-4 py-3">
              <div className="text-sm font-semibold text-zinc-950">模型快照</div>
              {predictionSnapshot ? (
                <div className="mt-2 grid gap-2 text-xs text-zinc-600">
                  <div>
                    版本 {predictionSnapshot.model_version || "-"}，生成时间{" "}
                    {predictionSnapshot.generated_at ? new Date(predictionSnapshot.generated_at).toLocaleString("zh-CN") : "-"}
                  </div>
                  <div>
                    胜平负概率：主胜 {Math.round(predictionSnapshot.p_home * 100)}%，平 {Math.round(predictionSnapshot.p_draw * 100)}%，客胜{" "}
                    {Math.round(predictionSnapshot.p_away * 100)}%
                  </div>
                  <div>
                    λH {predictionSnapshot.lambda_home?.toFixed(2) ?? "-"}，λA {predictionSnapshot.lambda_away?.toFixed(2) ?? "-"}，
                    置信 {predictionSnapshot.confidence != null ? `${Math.round(predictionSnapshot.confidence * 100)}%` : "-"}
                  </div>
                  <div>
                    EV：主 {predictionSnapshot.ev_home?.toFixed(3) ?? "-"} / 平 {predictionSnapshot.ev_draw?.toFixed(3) ?? "-"} / 客{" "}
                    {predictionSnapshot.ev_away?.toFixed(3) ?? "-"}
                  </div>
                  <div>
                    Kelly：主 {predictionSnapshot.kelly_home?.toFixed(3) ?? "-"} / 平 {predictionSnapshot.kelly_draw?.toFixed(3) ?? "-"} / 客{" "}
                    {predictionSnapshot.kelly_away?.toFixed(3) ?? "-"}
                  </div>
                </div>
              ) : (
                <EmptyState text="当前还没有持久化的预测快照，可能尚未执行过预测快照写入。" />
              )}
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard title="市场信号摘要" description="方便在独立详情页先判断这场比赛是否值得优先处理。">
          {marketTags.length > 0 ? (
            <div className="grid gap-3">
              <div className="flex flex-wrap gap-2">
                {marketTags.map((tag) => (
                  <StatusBadge key={tag.label} tone={tag.tone}>
                    {tag.label}
                  </StatusBadge>
                ))}
              </div>
              <div className="text-xs text-zinc-500">
                {marketIntel?.movement?.home_line_strength_delta != null ? (
                  <span>
                    盘口强度 {marketIntel.movement.home_line_strength_delta > 0 ? "+" : ""}
                    {marketIntel.movement.home_line_strength_delta.toFixed(2)}
                  </span>
                ) : null}
                {marketIntel?.alignment?.sporttery_minus_outer_handicap_median != null ? (
                  <span className={marketIntel?.movement?.home_line_strength_delta != null ? "ml-3" : ""}>
                    内外盘差 {marketIntel.alignment.sporttery_minus_outer_handicap_median > 0 ? "+" : ""}
                    {marketIntel.alignment.sporttery_minus_outer_handicap_median.toFixed(2)}
                  </span>
                ) : null}
              </div>
            </div>
          ) : (
            <EmptyState text="当前这场比赛没有明显的盘口或内外盘观察信号。" />
          )}
        </SurfaceCard>

        <SurfaceCard title="近期走势" description="展示双方最近已完赛记录，帮助判断近期状态与进失球趋势。">
          <div className="grid gap-4 lg:grid-cols-2">
            <RecentFormPanel title="主队近期" form={insights?.recent_form.home || null} />
            <RecentFormPanel title="客队近期" form={insights?.recent_form.away || null} />
          </div>
        </SurfaceCard>

        <SurfaceCard title="单场复盘" description="如果比赛已经结束，基于赛前快照给出这场比赛的复盘结果。">
          {backtestReview ? (
            <div className="grid gap-3">
              <div className="flex flex-wrap gap-2">
                <StatusBadge tone={backtestReview.hit ? "success" : "danger"}>
                  {backtestReview.hit ? "命中结果" : "未命中"}
                </StatusBadge>
                <StatusBadge tone="neutral">实际 {backtestReview.actual_outcome}</StatusBadge>
                <StatusBadge tone="neutral">预测 {backtestReview.predicted_outcome}</StatusBadge>
              </div>
              <div className="text-sm text-zinc-700">最终比分：{backtestReview.score}</div>
              <div className="text-xs text-zinc-500">单场 logloss：{backtestReview.logloss.toFixed(4)}</div>
            </div>
          ) : (
            <EmptyState text="当前还没有可展示的单场复盘。通常是比赛尚未结束，或赛前预测快照尚未写入。" />
          )}
        </SurfaceCard>

        <SurfaceCard
          title="助手解读"
          description="基于本页已有数据，自动生成结构化解读。若未配置 OpenRouter，会返回提示。"
        >
          <div className="grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setExplainMode("brief")}
                className={
                  explainMode === "brief"
                    ? "rounded-full bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white"
                    : "rounded-full bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-200"
                }
              >
                简版
              </button>
              <button
                type="button"
                onClick={() => setExplainMode("detailed")}
                className={
                  explainMode === "detailed"
                    ? "rounded-full bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white"
                    : "rounded-full bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-200"
                }
              >
                详细
              </button>
              <button
                type="button"
                onClick={runExplain}
                disabled={explainLoading}
                className="ml-auto rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {explainLoading ? "生成中…" : "生成解读"}
              </button>
            </div>

            {explainError ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{explainError}</div>
            ) : null}

            {explainContent ? (
              <div className="grid gap-3">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={copyExplain}
                    className="rounded-xl border border-zinc-200 px-3 py-2 text-xs text-zinc-700 hover:bg-zinc-50"
                  >
                    复制 Markdown
                  </button>
                  <button
                    type="button"
                    onClick={() => downloadText(`fixture_${fixtureId}_explain_${explainMode}.md`, explainContent)}
                    className="rounded-xl border border-zinc-200 px-3 py-2 text-xs text-zinc-700 hover:bg-zinc-50"
                  >
                    下载 .md
                  </button>
                  <button
                    type="button"
                    onClick={saveExplain}
                    className="rounded-xl border border-zinc-200 px-3 py-2 text-xs text-zinc-700 hover:bg-zinc-50"
                  >
                    本地保存
                  </button>
                  <button
                    type="button"
                    onClick={saveExplainToCloud}
                    disabled={cloudLoading}
                    className="rounded-xl border border-zinc-200 px-3 py-2 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
                  >
                    {cloudLoading ? "保存中…" : "保存到云端"}
                  </button>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-800 whitespace-pre-wrap">
                  {explainContent}
                </div>
              </div>
            ) : (
              <EmptyState text="点击“生成解读”，让助手基于本页数据输出判断要点与下一步建议。" />
            )}

            {cloudError ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                云端保存不可用：{cloudError}
              </div>
            ) : null}

            {saved.length > 0 ? (
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
                <div className="text-sm font-semibold text-zinc-950">本地已保存解读</div>
                <div className="mt-2 grid gap-2">
                  {saved.slice(0, 5).map((item) => (
                    <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-3 py-2">
                      <div className="text-xs text-zinc-600">
                        {new Date(item.created_at).toLocaleString("zh-CN")} · {item.mode === "brief" ? "简版" : "详细"}
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setExplainContent(item.content)}
                          className="rounded-lg border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50"
                        >
                          加载
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteSnapshot(item.id)}
                          className="rounded-lg border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-2 text-xs text-zinc-500">说明：本地保存仅存浏览器本地，不写入数据库。</div>
              </div>
            ) : null}

            <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold text-zinc-950">云端已保存解读</div>
                <StatusBadge tone="neutral">{cloudLoading ? "加载中…" : `${cloudSaved.length} 条`}</StatusBadge>
              </div>
              {cloudSaved.length > 0 ? (
                <div className="mt-2 grid gap-2">
                  {cloudSaved.slice(0, 8).map((item) => (
                    <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-3 py-2">
                      <div className="text-xs text-zinc-600">
                        {new Date(item.created_at).toLocaleString("zh-CN")} · {item.mode === "brief" ? "简版" : "详细"}
                      </div>
                      <button
                        type="button"
                        onClick={() => setExplainContent(item.content)}
                        className="rounded-lg border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50"
                      >
                        加载
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2">
                  <EmptyState text="暂无云端保存记录。你可以先生成解读，再点“保存到云端”。" />
                </div>
              )}
              <div className="mt-2 text-xs text-zinc-500">说明：云端保存写入 Supabase，适合多人共享与审计。</div>
            </div>
          </div>
        </SurfaceCard>

        <SurfaceCard title="下一步操作" description="从单场详情继续进入列表页、预测页或助手解释。">
          <div className="grid gap-3 text-sm">
            <Link
              href={backDate ? `/fixtures?date=${backDate}` : "/fixtures"}
              className="rounded-xl border border-zinc-200 px-4 py-3 hover:bg-zinc-50"
            >
              回到比赛页继续筛选其他比赛
            </Link>
            <Link
              href={backDate ? `/predictions?date=${backDate}` : "/predictions"}
              className="rounded-xl border border-zinc-200 px-4 py-3 hover:bg-zinc-50"
            >
              回到预测页对比其他场次
            </Link>
            <Link href="/chat" className="rounded-xl border border-zinc-200 px-4 py-3 hover:bg-zinc-50">
              让助手解释这场比赛的预测和盘口信号
            </Link>
          </div>
        </SurfaceCard>
      </section>
    </div>
  );
}

function RecentFormPanel({
  title,
  form,
}: {
  title: string;
  form: FixtureInsightResponse["recent_form"]["home"];
}) {
  return (
    <div className="rounded-xl border border-zinc-200 px-4 py-3">
      <div className="text-sm font-semibold text-zinc-950">
        {title}
        {form?.team_name ? <span className="ml-2 text-zinc-500">{form.team_name}</span> : null}
      </div>
      {form && form.matches.length > 0 ? (
        <div className="mt-3 grid gap-2">
          {form.matches.map((match) => (
            <div key={match.fixture_id} className="rounded-lg bg-zinc-50 px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-zinc-900">{match.opponent || "对手未知"}</div>
                <StatusBadge
                  tone={match.result === "W" ? "success" : match.result === "L" ? "danger" : "neutral"}
                >
                  {match.result || "-"}
                </StatusBadge>
              </div>
              <div className="mt-1 text-zinc-600">
                {match.competition || "赛事未知"} · {match.venue === "home" ? "主场" : "客场"} · {match.goals_for ?? "-"}-{match.goals_against ?? "-"}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3">
          <EmptyState text="暂无近期已完赛记录。" />
        </div>
      )}
    </div>
  );
}
