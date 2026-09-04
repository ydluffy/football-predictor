import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";

type FixtureRow = {
  fixture_id: number;
  competition_code: string | null;
  competition_name: string | null;
  utc_date: string | null;
  status: string | null;
  home_team_id: number | null;
  home_team_name: string | null;
  away_team_id: number | null;
  away_team_name: string | null;
  home_score: number | null;
  away_score: number | null;
};

type PredictionSnapshotRow = {
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

type OddsRow = {
  odds_home: number | null;
  odds_draw: number | null;
  odds_away: number | null;
};

type RecentRow = {
  fixture_id: number;
  utc_date: string | null;
  competition_code: string | null;
  competition_name: string | null;
  home_team_id: number | null;
  home_team_name: string | null;
  away_team_id: number | null;
  away_team_name: string | null;
  home_score: number | null;
  away_score: number | null;
};

function safeLog(x: number) {
  return Math.log(Math.max(1e-12, x));
}

function outcomeFromScores(home: number, away: number) {
  if (home > away) return "H" as const;
  if (home < away) return "A" as const;
  return "D" as const;
}

function predictedOutcome(pHome: number, pDraw: number, pAway: number) {
  if (pHome >= pDraw && pHome >= pAway) return "H" as const;
  if (pDraw >= pAway) return "D" as const;
  return "A" as const;
}

async function recentFormForTeam(sb: ReturnType<typeof supabaseAdmin>, teamId: number, teamName: string | null) {
  const { data, error } = await sb
    .from("fixtures")
    .select(
      "fixture_id,utc_date,competition_code,competition_name,home_team_id,home_team_name,away_team_id,away_team_name,home_score,away_score",
    )
    .eq("status", "FINISHED")
    .or(`home_team_id.eq.${teamId},away_team_id.eq.${teamId}`)
    .order("utc_date", { ascending: false })
    .limit(5);
  if (error) throw new Error(error.message);

  const matches = ((data || []) as RecentRow[]).map((row) => {
    const isHome = row.home_team_id === teamId;
    const gf = isHome ? row.home_score : row.away_score;
    const ga = isHome ? row.away_score : row.home_score;
    let result: "W" | "D" | "L" | null = null;
    if (typeof gf === "number" && typeof ga === "number") {
      result = gf > ga ? "W" : gf < ga ? "L" : "D";
    }
    return {
      fixture_id: row.fixture_id,
      utc_date: row.utc_date,
      competition: row.competition_name || row.competition_code,
      opponent: isHome ? row.away_team_name : row.home_team_name,
      venue: isHome ? "home" : "away",
      goals_for: gf,
      goals_against: ga,
      result,
    };
  });

  return {
    team_name: teamName,
    matches,
  };
}

export async function GET(_: Request, context: { params: Promise<{ fixtureId: string }> }) {
  const params = await context.params;
  const fixtureId = Number(params.fixtureId);
  if (!Number.isFinite(fixtureId)) {
    return NextResponse.json({ error: "invalid fixture_id" }, { status: 400 });
  }

  const { sb, response } = requireSupabaseAdmin();
  if (!sb) return response;
  const { data: fixtureData, error: fixtureError } = await sb
    .from("fixtures")
    .select(
      "fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name,home_score,away_score",
    )
    .eq("fixture_id", fixtureId)
    .maybeSingle();

  if (fixtureError) return NextResponse.json({ error: fixtureError.message }, { status: 500 });
  if (!fixtureData) return NextResponse.json({ error: "fixture not found" }, { status: 404 });

  const fixture = fixtureData as FixtureRow;

  const [{ data: predData, error: predError }, { data: oddsData, error: oddsError }, homeForm, awayForm] =
    await Promise.all([
      sb
        .from("fixture_predictions")
        .select(
          "model_version,as_of_date,generated_at,p_home,p_draw,p_away,confidence,lambda_home,lambda_away,odds_home,odds_draw,odds_away,ev_home,ev_draw,ev_away,kelly_home,kelly_draw,kelly_away",
        )
        .eq("fixture_id", fixtureId)
        .maybeSingle(),
      sb.from("odds").select("odds_home,odds_draw,odds_away").eq("fixture_id", fixtureId).maybeSingle(),
      fixture.home_team_id
        ? recentFormForTeam(sb, fixture.home_team_id, fixture.home_team_name)
        : Promise.resolve(null),
      fixture.away_team_id
        ? recentFormForTeam(sb, fixture.away_team_id, fixture.away_team_name)
        : Promise.resolve(null),
    ]);

  if (predError) return NextResponse.json({ error: predError.message }, { status: 500 });
  if (oddsError) return NextResponse.json({ error: oddsError.message }, { status: 500 });

  const predictionSnapshot = (predData || null) as PredictionSnapshotRow | null;
  const oddsSnapshot = (oddsData || null) as OddsRow | null;

  let backtestReview = null as null | {
    actual_outcome: "H" | "D" | "A";
    predicted_outcome: "H" | "D" | "A";
    hit: boolean;
    score: string;
    logloss: number;
  };

  if (
    fixture.status === "FINISHED" &&
    typeof fixture.home_score === "number" &&
    typeof fixture.away_score === "number" &&
    predictionSnapshot
  ) {
    const actual = outcomeFromScores(fixture.home_score, fixture.away_score);
    const pred = predictedOutcome(predictionSnapshot.p_home, predictionSnapshot.p_draw, predictionSnapshot.p_away);
    const actualProb =
      actual === "H"
        ? predictionSnapshot.p_home
        : actual === "D"
          ? predictionSnapshot.p_draw
          : predictionSnapshot.p_away;
    backtestReview = {
      actual_outcome: actual,
      predicted_outcome: pred,
      hit: actual === pred,
      score: `${fixture.home_score}-${fixture.away_score}`,
      logloss: -safeLog(actualProb),
    };
  }

  return NextResponse.json({
    odds_snapshot: oddsSnapshot,
    prediction_snapshot: predictionSnapshot,
    recent_form: {
      home: homeForm,
      away: awayForm,
    },
    backtest_review: backtestReview,
  });
}
