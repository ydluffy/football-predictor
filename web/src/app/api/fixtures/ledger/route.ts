import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
type AnalysisRunRow = {
  sales_day: string;
  stage: string | null;
  analysis_at: string | null;
  task_key: string | null;
  status: string | null;
  official_on_sale_count: number | null;
  real_plan_count: number | null;
  total_stake: number | null;
  plan_ids: string[] | null;
  fixed_shadow_recorded: boolean | null;
  fixed_shadow_plan_id: string | null;
  report: string | null;
  payload?: Record<string, unknown> | null;
};

type FixtureLedgerDbRow = {
  fixture_id: number;
  competition_code: string | null;
  competition_name: string | null;
  utc_date: string | null;
  status: string | null;
  home_team_id: number | null;
  home_team_name: string | null;
  away_team_id: number | null;
  away_team_name: string | null;
  home_score?: number | null;
  away_score?: number | null;
  sporttery_match_number?: string | null;
};

function normalizePlanStage(stage?: string | null) {
  if (stage === "final") return "终版方案";
  if (stage === "early") return "早盘方案";
  if (stage === "early_observation_only") return "早盘观察";
  if (stage === "final_observation_only") return "终版观察";
  return stage || "未知批次";
}

function isMissingColumnError(message?: string | null) {
  return /column .* does not exist/i.test(String(message || ""));
}

function isMissingRelationError(message?: string | null) {
  const text = String(message || "");
  return /relation .* does not exist/i.test(text) || /Could not find the table .* in the schema cache/i.test(text);
}

// 从分析批次 payload 中提取官方 SPF 赔率变化（早→晚批次按时间顺序覆盖，取最新一笔）
type MovementChange = {
  before: Array<number | null>;
  after: Array<number | null>;
  changed: boolean;
  captured_at: string | null;
};

function toOddsTriple(raw: unknown): Array<number | null> {
  if (!Array.isArray(raw)) return [null, null, null];
  const parse = (value: unknown) => {
    const num = Number(value);
    return Number.isFinite(num) && num > 1 ? num : null;
  };
  return [parse(raw[0]), parse(raw[1]), parse(raw[2])];
}

function extractMovementChanges(runs: Array<{ analysis_at: string | null; payload?: Record<string, unknown> | null }>) {
  const map = new Map<string, MovementChange>();
  for (const run of runs) {
    const movement = run.payload?.movement;
    if (!Array.isArray(movement)) continue;
    for (const entry of movement) {
      if (!entry || typeof entry !== "object") continue;
      const record = entry as Record<string, unknown>;
      const number = normalizeMatchNumber(String(record.number || ""));
      if (!number) continue;
      const before = toOddsTriple(record.spf_before);
      const after = toOddsTriple(record.spf_after);
      map.set(number, {
        before,
        after,
        changed: JSON.stringify(before) !== JSON.stringify(after),
        captured_at: run.analysis_at || null,
      });
    }
  }
  return map;
}

function salesDayUtcRange(requestedDate: string) {
  const from = new Date(`${requestedDate}T00:00:00.000Z`).toISOString();
  const to = new Date(new Date(`${requestedDate}T00:00:00.000Z`).getTime() + 24 * 3600 * 1000).toISOString();
  return { from, to };
}

function normalizeMatchNumber(raw: string) {
  const digits = raw.replace(/[^\d]/g, "");
  if (!digits) return null;
  return digits.padStart(3, "0");
}

function expandScopeNumbers(scope: unknown) {
  const values = Array.isArray(scope) ? scope : typeof scope === "string" ? scope.split(/[,\s/]+/) : [];
  const out = new Set<string>();
  for (const value of values) {
    const text = String(value || "").trim();
    if (!text) continue;
    const range = text.match(/^(\d{1,3})-(\d{1,3})$/);
    if (range) {
      const start = Number(range[1]);
      const end = Number(range[2]);
      if (Number.isFinite(start) && Number.isFinite(end) && end >= start) {
        for (let current = start; current <= end; current += 1) out.add(String(current).padStart(3, "0"));
        continue;
      }
    }
    const normalized = normalizeMatchNumber(text);
    if (normalized) out.add(normalized);
  }
  return [...out];
}

export async function GET(req: Request) {
  try {
    const { sb, response } = requireSupabaseAdmin(req);
    if (!sb) return response;

    const url = new URL(req.url);
    const requestedDate = url.searchParams.get("date");
    if (!requestedDate) {
      return NextResponse.json({ error: "missing date" }, { status: 400 });
    }

    const primaryFixturesResp = await sb
      .from("fixtures")
      .select(
        "fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name,home_score,away_score,sporttery_match_number"
      )
      .eq("sporttery_sales_day", requestedDate)
      .order("sporttery_match_number", { ascending: true })
      .order("utc_date", { ascending: true });

    let fixtureRows: FixtureLedgerDbRow[] = [];
    if (primaryFixturesResp.error && isMissingColumnError(primaryFixturesResp.error.message)) {
      const { from, to } = salesDayUtcRange(requestedDate);
      const fallbackResp = await sb
        .from("fixtures")
        .select("fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name,home_score,away_score")
        .gte("utc_date", from)
        .lt("utc_date", to)
        .order("utc_date", { ascending: true });
      if (fallbackResp.error) {
        return NextResponse.json({ error: fallbackResp.error.message }, { status: 500 });
      }
      fixtureRows = (fallbackResp.data || []) as FixtureLedgerDbRow[];
    } else {
      if (primaryFixturesResp.error) {
        return NextResponse.json({ error: primaryFixturesResp.error.message }, { status: 500 });
      }
      fixtureRows = (primaryFixturesResp.data || []) as FixtureLedgerDbRow[];
    }

    const fixtures = fixtureRows.map((row) => ({
      ...row,
      sporttery_match_number: row.sporttery_match_number ?? null,
    }));

    const fixtureIds = fixtures.map((item) => item.fixture_id);

    const runsResp = await sb
      .from("sporttery_analysis_runs")
      .select(
        "sales_day,stage,analysis_at,task_key,status,official_on_sale_count,real_plan_count,total_stake,plan_ids,fixed_shadow_recorded,fixed_shadow_plan_id,report,payload"
      )
      .eq("sales_day", requestedDate)
      .order("analysis_at", { ascending: true });

    const predictionResp =
      fixtureIds.length > 0
        ? await sb.from("fixture_predictions").select("fixture_id").in("fixture_id", fixtureIds)
        : { data: [], error: null };

    if (predictionResp.error && !isMissingColumnError(predictionResp.error.message)) {
      return NextResponse.json({ error: predictionResp.error.message }, { status: 500 });
    }
    if (runsResp.error && !isMissingColumnError(runsResp.error.message)) {
      return NextResponse.json({ error: runsResp.error.message }, { status: 500 });
    }

    const predictedIds = new Set<number>(((predictionResp.data || []) as Array<{ fixture_id: number }>).map((item) => item.fixture_id));

    const rawRuns = (runsResp.data || []) as AnalysisRunRow[];
    const movementByNumber = extractMovementChanges(rawRuns);
    const rows = fixtures.map((item) => ({
      ...item,
      has_prediction: predictedIds.has(item.fixture_id),
    }));

    const runs = rawRuns.map((item) => ({
      sales_day: item.sales_day,
      stage: item.stage || "unknown",
      stage_label: normalizePlanStage(item.stage),
      analysis_at: item.analysis_at,
      task_key: item.task_key,
      status: item.status,
      official_on_sale_count: item.official_on_sale_count,
      real_plan_count: Number(item.real_plan_count || 0),
      total_stake: Number(item.total_stake || 0),
      plan_ids: Array.isArray(item.plan_ids) ? item.plan_ids : [],
      fixed_shadow_recorded: Boolean(item.fixed_shadow_recorded),
      fixed_shadow_plan_id: item.fixed_shadow_plan_id,
      report: item.report,
      scope_match_numbers: expandScopeNumbers(item.payload?.scope),
    }));

    const runsByMatchNumber = new Map<string, typeof runs>();
    for (const run of runs) {
      for (const matchNumber of run.scope_match_numbers) {
        const list = runsByMatchNumber.get(matchNumber) || [];
        list.push(run);
        runsByMatchNumber.set(matchNumber, list);
      }
    }

    const rowsWithRunSummary = rows.map((item) => {
      const matchNumber = item.sporttery_match_number ? normalizeMatchNumber(item.sporttery_match_number) : null;
      const fixtureRuns = matchNumber ? runsByMatchNumber.get(matchNumber) || [] : [];
      const oddsChange = matchNumber ? movementByNumber.get(matchNumber) || null : null;
      return {
        ...item,
        analysis_run_count: fixtureRuns.length,
        analysis_stage_labels: fixtureRuns.map((run) => run.stage_label),
        latest_analysis_at: fixtureRuns.at(-1)?.analysis_at || null,
        odds_change: oddsChange,
      };
    });

    // 任务注册表：用于“当天流程跑到哪一步”的紧凑状态展示
    const registryResp = await sb
      .from("automation_task_registries")
      .select("sales_day,registry_updated_at,payload")
      .eq("sales_day", requestedDate)
      .maybeSingle();
    let registry: {
      updated_at: string | null;
      total_tasks: number;
      completed_tasks: number;
      scheduled_tasks: number;
      next_task: { key: string | null; run_at: string | null };
      tasks: Array<{ key: string; run_at: string | null; status: string | null; time_group: string | null; purpose: string | null }>;
    } | null = null;
    if (!registryResp.error || isMissingRelationError(registryResp.error?.message)) {
      const payload = (registryResp.data as any)?.payload;
      const tasks = Array.isArray(payload?.tasks) ? payload.tasks : [];
      const normalizedTasks = tasks
        .map((task: Record<string, unknown>) => ({
          key: String(task.key || ""),
          run_at: typeof task.run_at === "string" ? task.run_at : null,
          status: typeof task.status === "string" ? task.status : null,
          time_group: typeof task.time_group === "string" ? task.time_group : null,
          purpose: typeof task.purpose === "string" ? task.purpose : null,
        }))
        .sort((a: { run_at: string | null }, b: { run_at: string | null }) => String(a.run_at || "").localeCompare(String(b.run_at || "")));
      const nextTask = normalizedTasks.find((task: { status: string | null }) => task.status === "scheduled") || null;
      registry = {
        updated_at: (registryResp.data as any)?.registry_updated_at || null,
        total_tasks: normalizedTasks.length,
        completed_tasks: normalizedTasks.filter((task: { status: string | null }) => task.status === "completed").length,
        scheduled_tasks: normalizedTasks.filter((task: { status: string | null }) => task.status === "scheduled").length,
        next_task: { key: nextTask?.key || null, run_at: nextTask?.run_at || null },
        tasks: normalizedTasks,
      };
    }

    return NextResponse.json({
      sales_day: requestedDate,
      fixture_count: rowsWithRunSummary.length,
      predicted_fixture_count: predictedIds.size,
      analysis_run_count: runs.length,
      fixtures: rowsWithRunSummary,
      runs,
      registry,
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
