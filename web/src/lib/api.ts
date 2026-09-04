export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type ChatResponse = {
  content: string;
};

import { workbenchFetch } from "@/lib/workbenchClientAuth";

export type Fixture = {
  fixture_id: number;
  competition_code?: string | null;
  competition_name?: string | null;
  competition_name_zh?: string | null;
  utc_date?: string | null;
  kickoff_time_zh?: string | null;
  status?: string | null;
  status_zh?: string | null;
  home_team_id?: number | null;
  home_team_name?: string | null;
  home_team_name_zh?: string | null;
  away_team_id?: number | null;
  away_team_name?: string | null;
  away_team_name_zh?: string | null;
  home_score?: number | null;
  away_score?: number | null;
};

export type FixturesResponse = {
  date_from: string;
  date_to: string;
  count: number;
  fixtures: Fixture[];
};

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

export type ReviewsResponse = {
  summary_count: number;
  plan_count: number;
  summaries: ReviewSummary[];
  plans: ReviewPlanItem[];
};

export type FixtureResponse = {
  fixture: Fixture | null;
};

export type FixtureFormMatch = {
  fixture_id: number;
  utc_date: string | null;
  competition: string | null;
  opponent: string | null;
  venue: "home" | "away";
  goals_for: number | null;
  goals_against: number | null;
  result: "W" | "D" | "L" | null;
};

export type TeamRecentForm = {
  team_name: string | null;
  matches: FixtureFormMatch[];
};

export type FixturePredictionSnapshot = {
  model_version: string | null;
  as_of_date: string | null;
  generated_at: string | null;
  p_home: number;
  p_draw: number;
  p_away: number;
  confidence: number | null;
  lambda_home: number | null;
  lambda_away: number | null;
  odds_home: number | null;
  odds_draw: number | null;
  odds_away: number | null;
  ev_home: number | null;
  ev_draw: number | null;
  ev_away: number | null;
  kelly_home: number | null;
  kelly_draw: number | null;
  kelly_away: number | null;
};

export type FixtureOddsSnapshot = {
  odds_home: number | null;
  odds_draw: number | null;
  odds_away: number | null;
};

export type FixtureBacktestReview = {
  actual_outcome: "H" | "D" | "A";
  predicted_outcome: "H" | "D" | "A";
  hit: boolean;
  score: string;
  logloss: number;
};

export type FixtureInsightResponse = {
  odds_snapshot: FixtureOddsSnapshot | null;
  prediction_snapshot: FixturePredictionSnapshot | null;
  recent_form: {
    home: TeamRecentForm | null;
    away: TeamRecentForm | null;
  };
  backtest_review: FixtureBacktestReview | null;
};

export type FixtureExplainResponse = {
  content: string;
};

export type FixtureExplanationItem = {
  id: number;
  fixture_id: number;
  mode: "brief" | "detailed";
  content: string;
  created_at: string;
  source?: string | null;
};

export type FixtureExplanationListResponse = {
  count: number;
  items: FixtureExplanationItem[];
};

export type Prediction = {
  fixture_id: number;
  // 体彩赛程模式下，直接从 sporttery_match_analysis 提供的让球值（用于主表“让胜/让平/让负”展示）。
  // 传统 Supabase fixtures 模式下可能为空。
  sporttery_handicap?: number | null;
  p_home: number;
  p_draw: number;
  p_away: number;
  confidence: number;
  lambda_home: number;
  lambda_away: number;
  scorelines_top?: Array<{ home_goals: number; away_goals: number; p: number }>;
  p_over_2_5?: number;
  p_under_2_5?: number;
  p_btts_yes?: number;
  p_btts_no?: number;
  factors: string[];
  ev_home?: number;
  ev_draw?: number;
  ev_away?: number;
  kelly_home?: number;
  kelly_draw?: number;
  kelly_away?: number;
  betting_recommendation?: string;
  total_goals_suggestion?: string;
  correct_score_suggestion?: string;
  risk_note?: string;
};

export type PredictionsResponse = {
  count: number;
  predictions: Prediction[];
};

export type IngestResponse = {
  date_from: string;
  date_to: string;
  inserted_or_updated: number;
  db_path: string;
};

export type ChatContext = {
  // 用于让 /api/chat 了解“当前页面/当前销售日”等上下文，避免仅靠关键词猜测。
  page?: string;
  sales_day?: string; // YYYY-MM-DD
  // 预留：云端 Repo Agent 的仓库快照（可能来自 commit / zip / mirror）
  repo_snapshot_id?: string;
  // 预留：用于把“事实数据批次”与“对话决策”绑定起来（可追溯）
  pipeline_run_id?: string;
};

export type MarketMovement = {
  opening_captured_at: string | null;
  latest_captured_at: string | null;
  opening_home_handicap_median: number | null;
  latest_home_handicap_median: number | null;
  home_line_strength_delta: number | null;
  home_price_probability_delta: number | null;
  line_strength_per_hour: number | null;
  snapshot_count: number;
  bookmaker_count: number;
  favorite_hot_without_line_support: boolean;
  line_upgrade_without_price_support: boolean;
  line_downgrade: boolean;
  safe_for_shadow_features: boolean;
};

export type InnerOuterAlignment = {
  sporttery_handicap: number | null;
  outer_home_handicap_median: number | null;
  sporttery_minus_outer_handicap_median: number | null;
  aligned_bookmaker_count: number;
  time_aligned: boolean;
  min_time_delta_minutes: number | null;
  sporttery_captured_at: string | null;
  outer_captured_at: string | null;
};

export type FixtureMarketIntel = {
  fixture_id: number;
  movement: MarketMovement | null;
  alignment: InnerOuterAlignment | null;
};

export type MarketIntelResponse = {
  count: number;
  items: FixtureMarketIntel[];
};

export type DashboardContextResponse = {
  active_sales_day: string;
  sales_window: {
    sales_day: string;
    source: string;
    stage: string | null;
    scanned_at: string | null;
    window_start: string | null;
    window_end: string | null;
    batch_status: string | null;
    message: string | null;
  };
  registry: {
    updated_at: string | null;
    total_tasks: number;
    completed_tasks: number;
    scheduled_tasks: number;
    next_task_key: string | null;
    next_run_at: string | null;
  };
  betting_plans: {
    count: number;
    stages: Array<{
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
    }>;
  };
  market_signal_availability: {
    has_alignment_file: boolean;
    has_movement_file: boolean;
    mode: string;
    note: string;
  };
  system_status: {
    env: {
      hasSupabaseUrl: boolean;
      hasSupabaseServiceRole: boolean;
      hasFootballDataKey: boolean;
      hasOpenRouterKey: boolean;
      hasApiFootballKey?: boolean;
    };
    supabase: {
      ok: boolean | null;
      fixturesCount: number | null;
      error: string | null;
    };
  };
};

function apiBase(): string {
  return "";
}

export async function postChat(messages: ChatMessage[], context?: ChatContext): Promise<ChatResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, context }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as ChatResponse;
}

export async function ingestFootballData(dateFrom: string, dateTo: string): Promise<IngestResponse> {
  const url = `${apiBase()}/api/ingest/football-data?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`;
  const resp = await workbenchFetch(url, { method: "POST" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as IngestResponse;
}

export async function getFixtures(date: string): Promise<FixturesResponse> {
  const url = `${apiBase()}/api/fixtures?date=${encodeURIComponent(date)}`;
  const resp = await workbenchFetch(url, { cache: "no-store" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as FixturesResponse;
}

export async function getPredictionsByDate(date: string): Promise<PredictionsResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/predictions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as PredictionsResponse;
}

export async function getFixtureById(fixtureId: number): Promise<FixtureResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/fixtures/${fixtureId}`, { cache: "no-store" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as FixtureResponse;
}

export async function getPredictionsByFixtureIds(fixtureIds: number[]): Promise<PredictionsResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/predictions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fixture_ids: fixtureIds }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as PredictionsResponse;
}

export async function getFixtureInsights(fixtureId: number): Promise<FixtureInsightResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/fixtures/${fixtureId}/insights`, { cache: "no-store" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as FixtureInsightResponse;
}

export async function explainFixture(fixtureId: number, mode: "brief" | "detailed" = "brief"): Promise<FixtureExplainResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/fixtures/${fixtureId}/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as FixtureExplainResponse;
}

export async function listFixtureExplanations(fixtureId: number): Promise<FixtureExplanationListResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/fixtures/${fixtureId}/explanations`, { cache: "no-store" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as FixtureExplanationListResponse;
}

export async function saveFixtureExplanation(
  fixtureId: number,
  payload: { mode: "brief" | "detailed"; content: string; source?: string; meta?: unknown },
): Promise<{ item: FixtureExplanationItem }> {
  const resp = await workbenchFetch(`${apiBase()}/api/fixtures/${fixtureId}/explanations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as { item: FixtureExplanationItem };
}

export async function getMarketIntel(fixtures: Fixture[]): Promise<MarketIntelResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/market-intel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      fixtures: fixtures.map((fixture) => ({
        fixture_id: fixture.fixture_id,
        utc_date: fixture.utc_date ?? null,
        home_team_name: fixture.home_team_name ?? null,
        home_team_name_zh: fixture.home_team_name_zh ?? null,
        away_team_name: fixture.away_team_name ?? null,
        away_team_name_zh: fixture.away_team_name_zh ?? null,
      })),
    }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as MarketIntelResponse;
}

export async function getReviews(): Promise<ReviewsResponse> {
  const resp = await workbenchFetch(`${apiBase()}/api/reviews`, { cache: "no-store" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as ReviewsResponse;
}

export async function getDashboardContext(): Promise<DashboardContextResponse> {
  const resp = await fetch(`${apiBase()}/api/dashboard/context`, { cache: "no-store" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as DashboardContextResponse;
}

