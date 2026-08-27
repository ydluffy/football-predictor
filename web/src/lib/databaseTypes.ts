export type FixtureListRow = {
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
};

export type RecentFinishedMatchRow = {
  utc_date: string | null;
  home_team_id: number | null;
  away_team_id: number | null;
  home_score: number | null;
  away_score: number | null;
};

export type LeagueScoreRow = {
  home_score: number | null;
  away_score: number | null;
};

export type OddsRow = {
  fixture_id: number;
  odds_home: number | null;
  odds_draw: number | null;
  odds_away: number | null;
};

export type PredictionApiItem = {
  fixture_id: number;
  p_home: number;
  p_draw: number;
  p_away: number;
  confidence: number;
  lambda_home: number;
  lambda_away: number;
  p_over_2_5?: number;
  p_under_2_5?: number;
  p_btts_yes?: number;
  p_btts_no?: number;
  odds_home?: number | null;
  odds_draw?: number | null;
  odds_away?: number | null;
  bookmaker?: string | null;
  ev_home?: number | null;
  ev_draw?: number | null;
  ev_away?: number | null;
  kelly_home?: number | null;
  kelly_draw?: number | null;
  kelly_away?: number | null;
};
