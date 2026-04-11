import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { winDrawLoseFromLambdas } from "@/lib/poisson";
import { evAndKelly } from "@/lib/kelly";
import { competitionNameZh, formatLocalTimeFromUtc, statusZh, teamNameZh } from "@/lib/zh";

type PredictionOut = {
  fixture_id: number;
  competition_code?: string;
  competition_name?: string | null;
  competition_name_zh?: string;
  utc_date?: string | null;
  kickoff_time_zh?: string;
  status?: string | null;
  status_zh?: string;
  home_team_name?: string | null;
  home_team_name_zh?: string;
  away_team_name?: string | null;
  away_team_name_zh?: string;
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

function mean(nums: number[]) {
  if (!nums.length) return 0;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function clamp(x: number, a: number, b: number) {
  return Math.max(a, Math.min(b, x));
}

async function fetchRecentFinishedMatches(sb: ReturnType<typeof supabaseAdmin>, competitionCode: string, teamId: number, limit = 20) {
  const { data, error } = await sb
    .from("fixtures")
    .select("utc_date,home_team_id,away_team_id,home_score,away_score")
    .eq("competition_code", competitionCode)
    .eq("status", "FINISHED")
    .or(`home_team_id.eq.${teamId},away_team_id.eq.${teamId}`)
    .order("utc_date", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return data || [];
}

async function fetchLeagueAverages(sb: ReturnType<typeof supabaseAdmin>, competitionCode: string, limit = 500) {
  const { data, error } = await sb
    .from("fixtures")
    .select("home_score,away_score")
    .eq("competition_code", competitionCode)
    .eq("status", "FINISHED")
    .order("utc_date", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  const homeGoals = (data || []).map((r: any) => r.home_score).filter((x: any) => typeof x === "number") as number[];
  const awayGoals = (data || []).map((r: any) => r.away_score).filter((x: any) => typeof x === "number") as number[];
  return {
    avgHome: mean(homeGoals) || 1.35,
    avgAway: mean(awayGoals) || 1.05,
    sample: Math.min(homeGoals.length, awayGoals.length),
  };
}

function teamStats(matches: any[], teamId: number) {
  const gf: number[] = [];
  const ga: number[] = [];
  for (const m of matches) {
    const hs = typeof m.home_score === "number" ? m.home_score : null;
    const as = typeof m.away_score === "number" ? m.away_score : null;
    if (hs === null || as === null) continue;
    if (m.home_team_id === teamId) {
      gf.push(hs);
      ga.push(as);
    } else if (m.away_team_id === teamId) {
      gf.push(as);
      ga.push(hs);
    }
  }
  return { gfAvg: mean(gf), gaAvg: mean(ga), n: gf.length };
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { date?: string; fixture_ids?: number[] };
  const sb = supabaseAdmin();

  let fixtures: any[] = [];

  if (body.fixture_ids?.length) {
    const { data, error } = await sb
      .from("fixtures")
      .select("fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name")
      .in("fixture_id", body.fixture_ids);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    fixtures = data || [];
  } else if (body.date) {
    const from = new Date(`${body.date}T00:00:00.000Z`).toISOString();
    const to = new Date(new Date(`${body.date}T00:00:00.000Z`).getTime() + 24 * 3600 * 1000).toISOString();
    const { data, error } = await sb
      .from("fixtures")
      .select("fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name")
      .gte("utc_date", from)
      .lt("utc_date", to)
      .order("utc_date", { ascending: true });
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    fixtures = data || [];
  } else {
    return NextResponse.json({ error: "missing date or fixture_ids" }, { status: 400 });
  }

  const predictions: PredictionOut[] = [];

  // Fetch odds if available
  const fixtureIds = fixtures.map((f) => f.fixture_id);
  let oddsMap = new Map<number, { odds_home: number | null; odds_draw: number | null; odds_away: number | null }>();
  if (fixtureIds.length) {
    const { data: oddsRows } = await sb.from("odds").select("fixture_id,odds_home,odds_draw,odds_away").in("fixture_id", fixtureIds);
    for (const r of oddsRows || []) {
      oddsMap.set(r.fixture_id, { odds_home: r.odds_home, odds_draw: r.odds_draw, odds_away: r.odds_away });
    }
  }

  for (const f of fixtures) {
    const competitionCode = f.competition_code || "";
    const homeId = f.home_team_id;
    const awayId = f.away_team_id;
    if (!competitionCode || !homeId || !awayId) continue;

    const leagueAvg = await fetchLeagueAverages(sb, competitionCode);
    const homeRecent = await fetchRecentFinishedMatches(sb, competitionCode, homeId, 20);
    const awayRecent = await fetchRecentFinishedMatches(sb, competitionCode, awayId, 20);

    const home = teamStats(homeRecent, homeId);
    const away = teamStats(awayRecent, awayId);

    const homeAttack = home.n >= 5 ? clamp((home.gfAvg || leagueAvg.avgHome) / leagueAvg.avgHome, 0.6, 1.6) : 1.0;
    const homeDef = home.n >= 5 ? clamp((home.gaAvg || leagueAvg.avgAway) / leagueAvg.avgAway, 0.6, 1.6) : 1.0;
    const awayAttack = away.n >= 5 ? clamp((away.gfAvg || leagueAvg.avgAway) / leagueAvg.avgAway, 0.6, 1.6) : 1.0;
    const awayDef = away.n >= 5 ? clamp((away.gaAvg || leagueAvg.avgHome) / leagueAvg.avgHome, 0.6, 1.6) : 1.0;

    const lambdaHome = clamp(leagueAvg.avgHome * homeAttack * awayDef, 0.2, 3.5);
    const lambdaAway = clamp(leagueAvg.avgAway * awayAttack * homeDef, 0.2, 3.5);

    const probs = winDrawLoseFromLambdas(lambdaHome, lambdaAway, 8);

    const dataCompleteness = Math.min(1, (home.n + away.n) / 20);
    const entropy = -(
      probs.p_home * Math.log(probs.p_home + 1e-9) +
      probs.p_draw * Math.log(probs.p_draw + 1e-9) +
      probs.p_away * Math.log(probs.p_away + 1e-9)
    );
    const confidence = clamp((1.1 - entropy / 1.1) * 0.7 + dataCompleteness * 0.3, 0.05, 0.95);

    const factors: string[] = [];
    factors.push(`联赛均值 λH=${leagueAvg.avgHome.toFixed(2)} / λA=${leagueAvg.avgAway.toFixed(2)} (样本≈${leagueAvg.sample})`);
    factors.push(`主队近${home.n}场: 场均进球 ${home.gfAvg.toFixed(2)}，场均失球 ${home.gaAvg.toFixed(2)}`);
    factors.push(`客队近${away.n}场: 场均进球 ${away.gfAvg.toFixed(2)}，场均失球 ${away.gaAvg.toFixed(2)}`);
    factors.push(`推断 λH=${lambdaHome.toFixed(2)}，λA=${lambdaAway.toFixed(2)}`);

    const base: PredictionOut = {
      fixture_id: f.fixture_id,
      competition_code: f.competition_code,
      competition_name: f.competition_name ?? null,
      competition_name_zh: competitionNameZh(f.competition_code, f.competition_name),
      utc_date: f.utc_date ?? null,
      kickoff_time_zh: formatLocalTimeFromUtc(f.utc_date, "Asia/Shanghai"),
      status: f.status ?? null,
      status_zh: statusZh(f.status),
      home_team_name: f.home_team_name ?? null,
      home_team_name_zh: teamNameZh(f.home_team_name),
      away_team_name: f.away_team_name ?? null,
      away_team_name_zh: teamNameZh(f.away_team_name),
      p_home: probs.p_home,
      p_draw: probs.p_draw,
      p_away: probs.p_away,
      confidence,
      lambda_home: lambdaHome,
      lambda_away: lambdaAway,
      factors,
    };

    const o = oddsMap.get(f.fixture_id);
    if (o && (o.odds_home || o.odds_draw || o.odds_away)) {
      const ek = evAndKelly({ p_home: probs.p_home, p_draw: probs.p_draw, p_away: probs.p_away }, o, 0.25);
      predictions.push({ ...base, ...ek });
    } else {
      predictions.push(base);
    }
  }

  return NextResponse.json({ count: predictions.length, predictions });
}
