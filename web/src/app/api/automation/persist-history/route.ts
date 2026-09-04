import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";

type JsonRecord = Record<string, unknown>;

async function safeReadJsonFile(filePath: string): Promise<JsonRecord | null> {
  try {
    const raw = await readFile(filePath, "utf8");
    const trimmed = raw.trimStart();
    if (!trimmed) return null;
    // 有些产物可能是“说明文件/日志”但误用 .json 后缀；遇到这种直接跳过
    if (trimmed.startsWith("#")) return null;
    return JSON.parse(raw) as JsonRecord;
  } catch {
    return null;
  }
}

function asNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function reviewCategory(planId: string) {
  if (/FIXED_ODDS/i.test(planId)) return "固定赔率观察";
  if (/SAFE/i.test(planId)) return "稳健方案";
  if (/VALUE/i.test(planId)) return "价值方案";
  return "真实方案";
}

function parseReviewPlans(payload: JsonRecord) {
  const salesDay = asString(payload.reviewed_sales_day || payload.sales_day || payload.review_date);
  const reviewedAt = asString(payload.reviewed_at || payload.settled_at) || null;
  const items: Array<{
    sales_day: string;
    reviewed_at: string | null;
    plan_id: string;
    category: string;
    result: string;
    stake: number;
    payout: number;
    net_profit: number;
    roi: number | null;
    note: string | null;
    payload: JsonRecord;
  }> = [];

  if (Array.isArray(payload.real_plans)) {
    for (const raw of payload.real_plans as JsonRecord[]) {
      const planId = asString(raw.plan_id, "未命名方案");
      items.push({
        sales_day: salesDay,
        reviewed_at: reviewedAt,
        plan_id: planId,
        category: reviewCategory(planId),
        result: asString(raw.result, "待结算"),
        stake: asNumber(raw.stake),
        payout: asNumber(raw.payout),
        net_profit: asNumber(raw.net_profit),
        roi: typeof raw.roi === "number" ? raw.roi : null,
        note: asString(raw.legs || raw.breaking_leg || raw.breaking_legs || raw.classification, "") || null,
        payload: raw,
      });
    }
  }

  const fixedOdds =
    typeof payload.fixed_odds_shadow === "object" && payload.fixed_odds_shadow !== null
      ? (payload.fixed_odds_shadow as JsonRecord)
      : null;

  if (fixedOdds && Array.isArray(fixedOdds.plans)) {
    for (const raw of fixedOdds.plans as JsonRecord[]) {
      const planId = asString(raw.plan_id, "固定赔率观察");
      items.push({
        sales_day: salesDay,
        reviewed_at: reviewedAt,
        plan_id: planId,
        category: "固定赔率观察",
        result: asString(raw.result, "待结算"),
        stake: asNumber(raw.stake),
        payout: asNumber(raw.payout),
        net_profit: asNumber(raw.net_profit),
        roi: typeof raw.roi === "number" ? raw.roi : null,
        note: asString(raw.breaking_leg || raw.breaking_legs || raw.odds, "") || null,
        payload: raw,
      });
    }
  } else if (fixedOdds && fixedOdds.plan_id) {
    const planId = asString(fixedOdds.plan_id, "固定赔率观察");
    items.push({
      sales_day: salesDay,
      reviewed_at: reviewedAt,
      plan_id: planId,
      category: "固定赔率观察",
      result: asString(fixedOdds.result, "待结算"),
      stake: asNumber(fixedOdds.stake),
      payout: asNumber(fixedOdds.payout),
      net_profit: asNumber(fixedOdds.net_profit),
      roi: typeof fixedOdds.roi === "number" ? fixedOdds.roi : null,
      note: asString(fixedOdds.breaking_leg || fixedOdds.breaking_legs || fixedOdds.odds, "") || null,
      payload: fixedOdds,
    });
  }

  return items;
}

function parseReviewSummary(payload: JsonRecord) {
  const salesDay = asString(payload.reviewed_sales_day || payload.sales_day || payload.review_date);
  const reviewedAt = asString(payload.reviewed_at || payload.settled_at) || null;
  const summary =
    typeof payload.real_summary === "object" && payload.real_summary !== null
      ? (payload.real_summary as JsonRecord)
      : typeof payload.real_plans === "object" && payload.real_plans !== null
        ? (payload.real_plans as JsonRecord)
        : null;

  return {
    sales_day: salesDay,
    reviewed_at: reviewedAt,
    status: asString(payload.status, "unknown"),
    plans: asNumber(summary?.plans || summary?.count),
    hits: asNumber(summary?.hits),
    misses: asNumber(summary?.misses),
    stake: asNumber(summary?.stake),
    payout: asNumber(summary?.payout),
    net_profit: asNumber(summary?.net_profit),
    roi: typeof summary?.roi === "number" ? summary.roi : null,
    payload,
  };
}

async function resolveDataDir() {
  const cwd = process.cwd();
  const candidates = [
    path.resolve(cwd, "..", "football-predictor", "artifacts", "data"),
    path.resolve(cwd, "football-predictor", "artifacts", "data"),
  ];
  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }
  return null;
}

export async function POST(req: Request) {
  try {
    const { sb, response } = requireSupabaseAdmin(req);
    if (!sb) return response;

    const body = (await req.json().catch(() => ({}))) as { sales_days?: string[] };
    const wantedSalesDays = new Set((body.sales_days || []).map((v) => String(v)));
    const dataDir = await resolveDataDir();
    if (!dataDir) {
      return NextResponse.json({ error: "未找到本地 artifacts/data 目录" }, { status: 400 });
    }

    const fileNames = await readdir(/* turbopackIgnore: true */ dataDir);
    const reviewFiles = fileNames.filter((name) => /^sporttery_daily_review_\d{4}-\d{2}-\d{2}_\d{4}\.json$/.test(name));
    const analysisFiles = fileNames.filter((name) => /^sporttery_.+\.json$/.test(name));

    const skipped: Array<{ file: string; reason: string }> = [];
    const reviewSummaries: any[] = [];
    const reviewPlans: any[] = [];
    for (const fileName of reviewFiles) {
      const fullPath = path.join(/* turbopackIgnore: true */ dataDir, fileName);
      const payload = await safeReadJsonFile(fullPath);
      if (!payload) {
        skipped.push({ file: fileName, reason: "invalid_json" });
        continue;
      }
      const salesDay = asString(payload.reviewed_sales_day || payload.sales_day || payload.review_date);
      if (wantedSalesDays.size > 0 && !wantedSalesDays.has(salesDay)) continue;
      reviewSummaries.push(parseReviewSummary(payload));
      reviewPlans.push(...parseReviewPlans(payload));
    }

    const analysisRuns: any[] = [];
    for (const fileName of analysisFiles) {
      const fullPath = path.join(/* turbopackIgnore: true */ dataDir, fileName);
      const payload = await safeReadJsonFile(fullPath);
      if (!payload) {
        skipped.push({ file: fileName, reason: "invalid_json" });
        continue;
      }
      const salesDay = asString(payload.sales_day);
      const analysisAt = asString(payload.analysis_at);
      if (!salesDay || !analysisAt) continue;
      if (wantedSalesDays.size > 0 && !wantedSalesDays.has(salesDay)) continue;
      if (!payload.stage && !payload.real_plans && !payload.real_plan && !payload.fixed_odds_shadow) continue;
      const realPlans =
        typeof payload.real_plans === "object" && payload.real_plans !== null ? (payload.real_plans as JsonRecord) : null;
      const fixedOdds =
        typeof payload.fixed_odds_shadow === "object" && payload.fixed_odds_shadow !== null
          ? (payload.fixed_odds_shadow as JsonRecord)
          : null;
      analysisRuns.push({
        sales_day: salesDay,
        stage: asString(payload.stage, "unknown"),
        analysis_at: analysisAt,
        task_key: asString(payload.task_key) || null,
        status: asString(payload.status) || null,
        official_on_sale_count: asNumber(payload.official_on_sale_count, 0) || null,
        real_plan_count: asNumber(realPlans?.rows_added || realPlans?.count),
        total_stake: asNumber(realPlans?.total_stake),
        plan_ids: Array.isArray(realPlans?.plan_ids) ? realPlans?.plan_ids : [],
        fixed_shadow_recorded: String(fixedOdds?.status || "").toLowerCase() === "recorded",
        fixed_shadow_plan_id: asString(fixedOdds?.plan_id) || null,
        report: asString(payload.report) || null,
        payload,
      });
    }

    if (reviewSummaries.length > 0) {
      const { error } = await sb.from("sporttery_review_summaries").upsert(reviewSummaries, { onConflict: "sales_day" });
      if (error) return NextResponse.json({ error: error.message, table: "sporttery_review_summaries" }, { status: 500 });
    }

    if (reviewPlans.length > 0) {
      const { error } = await sb.from("sporttery_review_plans").upsert(reviewPlans, { onConflict: "sales_day,plan_id,category" });
      if (error) return NextResponse.json({ error: error.message, table: "sporttery_review_plans" }, { status: 500 });
    }

    if (analysisRuns.length > 0) {
      const { error } = await sb
        .from("sporttery_analysis_runs")
        .upsert(analysisRuns, { onConflict: "sales_day,stage,analysis_at" });
      if (error) return NextResponse.json({ error: error.message, table: "sporttery_analysis_runs" }, { status: 500 });
    }

    return NextResponse.json({
      persisted_review_summaries: reviewSummaries.length,
      persisted_review_plans: reviewPlans.length,
      persisted_analysis_runs: analysisRuns.length,
      data_dir: dataDir,
      loaded_review_files: reviewFiles.length,
      loaded_analysis_files: analysisFiles.length,
      skipped_files: skipped.slice(0, 20),
      skipped_files_count: skipped.length,
    });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}
