export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type ChatResponse = {
  content: string;
};

export type Fixture = {
  fixture_id: number;
  competition_code?: string | null;
  competition_name?: string | null;
  utc_date?: string | null;
  status?: string | null;
  home_team_id?: number | null;
  home_team_name?: string | null;
  away_team_id?: number | null;
  away_team_name?: string | null;
  home_score?: number | null;
  away_score?: number | null;
};

export type FixturesResponse = {
  date_from: string;
  date_to: string;
  count: number;
  fixtures: Fixture[];
};

export type Prediction = {
  fixture_id: number;
  p_home: number;
  p_draw: number;
  p_away: number;
  confidence: number;
  lambda_home: number;
  lambda_away: number;
  factors: string[];
  ev_home?: number;
  ev_draw?: number;
  ev_away?: number;
  kelly_home?: number;
  kelly_draw?: number;
  kelly_away?: number;
  betting_recommendation?: string;
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

function apiBase(): string {
  return "";
}

export async function postChat(messages: ChatMessage[]): Promise<ChatResponse> {
  const resp = await fetch(`${apiBase()}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as ChatResponse;
}

export async function ingestFootballData(dateFrom: string, dateTo: string): Promise<IngestResponse> {
  const url = `${apiBase()}/api/ingest/football-data?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`;
  const resp = await fetch(url, { method: "POST" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as IngestResponse;
}

export async function getFixtures(date: string): Promise<FixturesResponse> {
  const url = `${apiBase()}/api/fixtures?date=${encodeURIComponent(date)}`;
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as FixturesResponse;
}

export async function getPredictionsByDate(date: string): Promise<PredictionsResponse> {
  const resp = await fetch(`${apiBase()}/api/predictions`, {
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

