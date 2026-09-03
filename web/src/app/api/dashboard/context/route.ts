import { NextResponse } from "next/server";
import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { localArtifactsEnabled } from "@/lib/localArtifacts";

type SalesWindowPayload = {
  stage?: string;
  sales_day?: string;
  scanned_at?: string;
  window_start?: string;
  window_end?: string;
  batch_status?: string;
  message?: string;
};

type TaskRegistryPayload = {
  sales_day?: string;
  updated_at?: string;
  tasks?: Array<{
    key?: string;
    run_at?: string;
    time_group?: string;
    purpose?: string;
    status?: string;
    match_numbers?: string[];
  }>;
};

type PlanArtifactPayload = {
  stage?: string;
  analysis_at?: string;
  scope?: string[];
  real_plans?: {
    rows_added?: number;
    total_stake?: number;
    plan_ids?: string[];
  };
  fixed_odds_shadow?: {
    status?: string;
    plan_id?: string;
    odds?: number;
    virtual_stake?: number;
    expected_payout?: number;
  };
  report?: string;
};

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

async function readJson<T>(filePath: string): Promise<T | null> {
  try {
    const raw = await readFile(filePath, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function nowShanghaiDateTime() {
  const now = new Date();
  const local = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
  const yyyy = local.getFullYear();
  const mm = String(local.getMonth() + 1).padStart(2, "0");
  const dd = String(local.getDate()).padStart(2, "0");
  const hh = String(local.getHours()).padStart(2, "0");
  const mi = String(local.getMinutes()).padStart(2, "0");
  return {
    date: `${yyyy}-${mm}-${dd}`,
    time: `${hh}:${mi}`,
    isoLike: `${yyyy}-${mm}-${dd}T${hh}:${mi}:00+08:00`,
  };
}

function isNowInsideWindow(window?: SalesWindowPayload | null) {
  if (!window?.window_start || !window?.window_end) return false;
  const now = Date.now();
  const start = new Date(window.window_start).getTime();
  const end = new Date(window.window_end).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return false;
  return now >= start && now <= end;
}

function normalizePlanStage(stage?: string) {
  if (stage === "final") return "终版投注方案";
  if (stage === "early") return "早盘投注方案";
  return "投注方案";
}

async function resolveActiveSalesWindow(dataDir: string | null) {
  if (!dataDir) {
    const now = nowShanghaiDateTime();
    return {
      sales_day: now.date,
      source: "shanghai_today_fallback",
      stage: null,
      scanned_at: null,
      window_start: null,
      window_end: null,
      batch_status: null,
      message: "未找到体彩销售窗产物，已回退到北京时间自然日。",
    };
  }

  const latestConfirm = await readJson<SalesWindowPayload>(
    path.join(dataDir, "sporttery_sales_window_scan_latest_confirm.json"),
  );
  const latestPreopen = await readJson<SalesWindowPayload>(
    path.join(dataDir, "sporttery_sales_window_scan_latest_preopen.json"),
  );

  const candidates = [
    latestConfirm ? { payload: latestConfirm, source: "latest_confirm" } : null,
    latestPreopen ? { payload: latestPreopen, source: "latest_preopen" } : null,
  ].filter(Boolean) as Array<{ payload: SalesWindowPayload; source: string }>;

  const activeCandidate = candidates.find((item) => isNowInsideWindow(item.payload));
  if (activeCandidate?.payload.sales_day) {
    return {
      sales_day: activeCandidate.payload.sales_day,
      source: activeCandidate.source,
      stage: activeCandidate.payload.stage || null,
      scanned_at: activeCandidate.payload.scanned_at || null,
      window_start: activeCandidate.payload.window_start || null,
      window_end: activeCandidate.payload.window_end || null,
      batch_status: activeCandidate.payload.batch_status || null,
      message: activeCandidate.payload.message || null,
    };
  }

  const newest = candidates
    .sort((a, b) => String(b.payload.scanned_at || "").localeCompare(String(a.payload.scanned_at || "")))[0]
    ?.payload;
  if (newest?.sales_day) {
    return {
      sales_day: newest.sales_day,
      source: "latest_scan_outside_window",
      stage: newest.stage || null,
      scanned_at: newest.scanned_at || null,
      window_start: newest.window_start || null,
      window_end: newest.window_end || null,
      batch_status: newest.batch_status || null,
      message: newest.message || null,
    };
  }

  const now = nowShanghaiDateTime();
  return {
    sales_day: now.date,
    source: "shanghai_today_fallback",
    stage: null,
    scanned_at: null,
    window_start: null,
    window_end: null,
    batch_status: null,
    message: "未找到可用销售窗产物，已回退到北京时间自然日。",
  };
}

async function loadTaskRegistry(dataDir: string | null, salesDay: string) {
  if (!dataDir) return null;
  return readJson<TaskRegistryPayload>(path.join(dataDir, `sporttery_task_registry_${salesDay}.json`));
}

async function loadPlanSummaries(dataDir: string | null, salesDay: string) {
  if (!dataDir) return [];
  const files = await readdir(dataDir);
  const matched = files.filter((name) => new RegExp(`^sporttery_(early|final)_analysis_${salesDay}_.+\\.json$`).test(name));
  const output: Array<{
    stage: string;
    stage_label: string;
    analysis_at: string | null;
    scope: string[];
    real_plan_count: number;
    total_stake: number;
    plan_ids: string[];
    fixed_shadow_recorded: boolean;
    fixed_shadow_plan_id: string | null;
    report: string | null;
  }> = [];

  for (const fileName of matched) {
    const payload = await readJson<PlanArtifactPayload>(path.join(dataDir, fileName));
    if (!payload) continue;
    output.push({
      stage: payload.stage || "unknown",
      stage_label: normalizePlanStage(payload.stage),
      analysis_at: payload.analysis_at || null,
      scope: Array.isArray(payload.scope) ? payload.scope : [],
      real_plan_count: Number(payload.real_plans?.rows_added || 0),
      total_stake: Number(payload.real_plans?.total_stake || 0),
      plan_ids: Array.isArray(payload.real_plans?.plan_ids) ? payload.real_plans?.plan_ids : [],
      fixed_shadow_recorded: payload.fixed_odds_shadow?.status === "recorded",
      fixed_shadow_plan_id: payload.fixed_odds_shadow?.plan_id || null,
      report: payload.report || null,
    });
  }

  return output.sort((a, b) => String(a.analysis_at || "").localeCompare(String(b.analysis_at || "")));
}

async function detectMarketSignalAvailability(dataDir: string | null, salesDay: string) {
  if (!dataDir) {
    return {
      has_alignment_file: false,
      has_movement_file: false,
      mode: "missing_all",
      note: "未找到市场信号产物目录。",
    };
  }
  const files = await readdir(dataDir);
  const hasAlignmentFile = files.some((name) => name.startsWith(`inner_outer_market_alignment_${salesDay}`) && name.endsWith(".csv"));
  const hasMovementFile = files.some((name) => name.startsWith(`handicap_market_movement_${salesDay}`) && name.endsWith(".csv"));

  return {
    has_alignment_file: hasAlignmentFile,
    has_movement_file: hasMovementFile,
    mode: hasAlignmentFile || hasMovementFile ? "sales_day_artifacts" : "fallback_only",
    note:
      hasAlignmentFile || hasMovementFile
        ? "当前销售日已找到市场信号产物。"
        : "当前销售日未找到盘口/内外盘对齐产物，首页将改用预测与投注方案兜底展示重点信号。",
  };
}

async function loadSystemStatus() {
  const hasSupabaseUrl = Boolean(process.env.SUPABASE_URL);
  const hasSupabaseServiceRole = Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY);
  const hasFootballDataKey = Boolean(process.env.FOOTBALL_DATA_API_KEY || process.env.FOOTBALLDATA_API_KEY);
  const hasOpenRouterKey = Boolean(process.env.OPENROUTER_API_KEY || process.env.OPEN_ROUTER_API_KEY);
  const hasApiFootballKey = Boolean(process.env.API_FOOTBALL_KEY);

  let supabaseOk: boolean | null = null;
  let fixturesCount: number | null = null;
  let supabaseError: string | null = null;
  if (hasSupabaseUrl && hasSupabaseServiceRole) {
    try {
      const sb = supabaseAdmin();
      const { count, error } = await sb.from("fixtures").select("fixture_id", { count: "exact", head: true });
      if (error) {
        supabaseOk = false;
        supabaseError = error.message;
      } else {
        supabaseOk = true;
        fixturesCount = typeof count === "number" ? count : null;
      }
    } catch (error) {
      supabaseOk = false;
      supabaseError = error instanceof Error ? error.message : String(error);
    }
  }

  return {
    env: {
      hasSupabaseUrl,
      hasSupabaseServiceRole,
      hasFootballDataKey,
      hasOpenRouterKey,
      hasApiFootballKey,
    },
    supabase: {
      ok: supabaseOk,
      fixturesCount,
      error: supabaseError,
    },
  };
}

export async function GET() {
  const dataDir = await firstExistingDir(dataDirCandidates());
  const activeSalesWindow = await resolveActiveSalesWindow(dataDir);
  const [taskRegistry, planSummaries, marketSignalAvailability, systemStatus] = await Promise.all([
    loadTaskRegistry(dataDir, activeSalesWindow.sales_day),
    loadPlanSummaries(dataDir, activeSalesWindow.sales_day),
    detectMarketSignalAvailability(dataDir, activeSalesWindow.sales_day),
    loadSystemStatus(),
  ]);

  const tasks = Array.isArray(taskRegistry?.tasks) ? taskRegistry.tasks : [];
  const completedTasks = tasks.filter((task) => task.status === "completed").length;
  const scheduledTasks = tasks.filter((task) => task.status === "scheduled").length;
  const nextTask = tasks.find((task) => task.status === "scheduled") || null;
  const totalPlanCount = planSummaries.reduce((sum, item) => sum + item.real_plan_count, 0);

  return NextResponse.json({
    active_sales_day: activeSalesWindow.sales_day,
    sales_window: activeSalesWindow,
    registry: {
      updated_at: taskRegistry?.updated_at || null,
      total_tasks: tasks.length,
      completed_tasks: completedTasks,
      scheduled_tasks: scheduledTasks,
      next_task_key: nextTask?.key || null,
      next_run_at: nextTask?.run_at || null,
    },
    betting_plans: {
      count: totalPlanCount,
      stages: planSummaries,
    },
    market_signal_availability: marketSignalAvailability,
    system_status: systemStatus,
  });
}
