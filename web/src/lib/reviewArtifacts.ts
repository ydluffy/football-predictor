import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { localArtifactsEnabled } from "@/lib/localArtifacts";

export type ReviewSummary = {
  sales_day: string;
  reviewed_at: string | null;
  status: string;
  plans: number;
  hits: number;
  misses: number;
  stake: number;
  payout: number;
  net_profit: number;
  roi: number | null;
  source_file: string;
};

export type ReviewPlanItem = {
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
};

type JsonRecord = Record<string, unknown>;

function dataDirCandidates() {
  if (!localArtifactsEnabled()) return [];
  const cwd = process.cwd();
  return [
    path.resolve(cwd, "..", "football-predictor", "artifacts", "data"),
    path.resolve(cwd, "football-predictor", "artifacts", "data"),
  ];
}

async function firstExistingDir(paths: string[]) {
  for (const candidate of paths) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }
  return null;
}

function asNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function normalizeResult(value: unknown) {
  const text = asString(value, "待结算");
  if (!text) return "待结算";
  return text;
}

function parseSummary(payload: JsonRecord, sourceFile: string): ReviewSummary {
  const salesDay = asString(payload.reviewed_sales_day || payload.sales_day || payload.review_date, "未知日期");
  const reviewedAt = asString(payload.reviewed_at || payload.settled_at, "") || null;
  const status = asString(payload.status, "unknown");

  const realSummary =
    typeof payload.real_summary === "object" && payload.real_summary !== null
      ? (payload.real_summary as JsonRecord)
      : null;
  const realPlans =
    typeof payload.real_plans === "object" && payload.real_plans !== null
      ? (payload.real_plans as JsonRecord)
      : null;

  if (realSummary) {
    return {
      sales_day: salesDay,
      reviewed_at: reviewedAt,
      status,
      plans: asNumber(realSummary.plans),
      hits: asNumber(realSummary.hits),
      misses: asNumber(realSummary.misses),
      stake: asNumber(realSummary.stake),
      payout: asNumber(realSummary.payout),
      net_profit: asNumber(realSummary.net_profit),
      roi: typeof realSummary.roi === "number" ? realSummary.roi : null,
      source_file: sourceFile,
    };
  }

  if (realPlans) {
    return {
      sales_day: salesDay,
      reviewed_at: reviewedAt,
      status,
      plans: asNumber(realPlans.count || realPlans.plans),
      hits: asNumber(realPlans.hits),
      misses: asNumber(realPlans.misses),
      stake: asNumber(realPlans.stake),
      payout: asNumber(realPlans.payout),
      net_profit: asNumber(realPlans.net_profit),
      roi: typeof realPlans.roi === "number" ? realPlans.roi : null,
      source_file: sourceFile,
    };
  }

  if (Array.isArray(payload.real_plans)) {
    const plans = payload.real_plans as JsonRecord[];
    const hits = plans.filter((item) => /命中|hit/i.test(asString(item.result))).length;
    const stake = plans.reduce((sum, item) => sum + asNumber(item.stake), 0);
    const payout = plans.reduce((sum, item) => sum + asNumber(item.payout), 0);
    const netProfit = plans.reduce((sum, item) => sum + asNumber(item.net_profit), 0);
    return {
      sales_day: salesDay,
      reviewed_at: reviewedAt,
      status,
      plans: plans.length,
      hits,
      misses: plans.length - hits,
      stake,
      payout,
      net_profit: netProfit,
      roi: stake > 0 ? netProfit / stake : null,
      source_file: sourceFile,
    };
  }

  return {
    sales_day: salesDay,
    reviewed_at: reviewedAt,
    status,
    plans: 0,
    hits: 0,
    misses: 0,
    stake: 0,
    payout: 0,
    net_profit: 0,
    roi: null,
    source_file: sourceFile,
  };
}

function parseRealPlanItems(payload: JsonRecord) {
  const salesDay = asString(payload.reviewed_sales_day || payload.sales_day || payload.review_date, "未知日期");
  const reviewedAt = asString(payload.reviewed_at || payload.settled_at, "") || null;
  const items: ReviewPlanItem[] = [];

  if (Array.isArray(payload.real_plans)) {
    for (const raw of payload.real_plans as JsonRecord[]) {
      items.push({
        sales_day: salesDay,
        reviewed_at: reviewedAt,
        plan_id: asString(raw.plan_id, "未命名方案"),
        category: /SAFE/i.test(asString(raw.plan_id)) ? "稳健方案" : /VALUE/i.test(asString(raw.plan_id)) ? "价值方案" : "真实方案",
        result: normalizeResult(raw.result),
        stake: asNumber(raw.stake),
        payout: asNumber(raw.payout),
        net_profit: asNumber(raw.net_profit),
        roi: typeof raw.roi === "number" ? raw.roi : null,
        note: asString(raw.legs || raw.breaking_leg || raw.classification, "") || null,
      });
    }
  }

  const realPlans =
    typeof payload.real_plans === "object" && payload.real_plans !== null
      ? (payload.real_plans as JsonRecord)
      : null;
  if (realPlans && Array.isArray(realPlans.details)) {
    for (const raw of realPlans.details as JsonRecord[]) {
      items.push({
        sales_day: salesDay,
        reviewed_at: reviewedAt,
        plan_id: asString(raw.plan_id, "未命名方案"),
        category: /SAFE/i.test(asString(raw.plan_id)) ? "稳健方案" : /VALUE/i.test(asString(raw.plan_id)) ? "价值方案" : "真实方案",
        result: normalizeResult(raw.result),
        stake: asNumber(raw.stake, 0),
        payout: asNumber(raw.payout),
        net_profit: asNumber(raw.net_profit),
        roi: typeof raw.roi === "number" ? raw.roi : null,
        note: asString(raw.legs || raw.failed_leg || raw.breaking_leg, "") || null,
      });
    }
  }

  const fixedOdds =
    typeof payload.fixed_odds_shadow === "object" && payload.fixed_odds_shadow !== null
      ? (payload.fixed_odds_shadow as JsonRecord)
      : null;
  if (fixedOdds && Array.isArray(fixedOdds.plans)) {
    for (const raw of fixedOdds.plans as JsonRecord[]) {
      items.push({
        sales_day: salesDay,
        reviewed_at: reviewedAt,
        plan_id: asString(raw.plan_id, "固定赔率观察"),
        category: "固定赔率观察",
        result: normalizeResult(raw.result),
        stake: asNumber(raw.stake),
        payout: asNumber(raw.payout),
        net_profit: asNumber(raw.net_profit),
        roi: typeof raw.roi === "number" ? raw.roi : null,
        note: asString(raw.breaking_leg || raw.breaking_legs || raw.odds, "") || null,
      });
    }
  }

  return items;
}

export async function loadReviewArtifacts(limit = 8) {
  const dataDir = await firstExistingDir(dataDirCandidates());
  if (!dataDir) {
    return { summaries: [] as ReviewSummary[], plans: [] as ReviewPlanItem[] };
  }

  const files = await readdir(/* turbopackIgnore: true */ dataDir);
  const targetFiles = files
    .filter((name) => /^sporttery_daily_review_\d{4}-\d{2}-\d{2}_\d{4}\.json$/.test(name))
    .sort((a, b) => b.localeCompare(a))
    .slice(0, limit);

  const summaries: ReviewSummary[] = [];
  const plans: ReviewPlanItem[] = [];

  for (const fileName of targetFiles) {
    const filePath = path.join(/* turbopackIgnore: true */ dataDir, fileName);
    const raw = await readFile(/* turbopackIgnore: true */ filePath, "utf8");
    const payload = JSON.parse(raw) as JsonRecord;
    summaries.push(parseSummary(payload, fileName));
    plans.push(...parseRealPlanItems(payload));
  }

  return { summaries, plans };
}
