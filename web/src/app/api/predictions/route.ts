import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { topScorelines, totalsProbs, winDrawLoseFromLambdas } from "@/lib/poisson";
import { evAndKelly } from "@/lib/kelly";
import { competitionNameZh, formatLocalTimeFromUtc, statusZh, teamNameZhMaybe } from "@/lib/zh";
import { translateTeamNamesWithCache } from "@/lib/translateTeamNames";
import type { FixtureListRow, LeagueScoreRow, OddsRow, RecentFinishedMatchRow } from "@/lib/databaseTypes";
import { loadSportteryFixturesBySalesDay, parseSportteryFixtureId } from "@/lib/sportteryFixtures";
import { loadSportteryPredictionSeedsBySalesDay } from "@/lib/sportteryPredictions";

type PredictionOut = {
  fixture_id: number;
  competition_code?: string | null;
  competition_name?: string | null;
  competition_name_zh?: string | null;
  utc_date?: string | null;
  kickoff_time_zh?: string;
  status?: string | null;
  status_zh?: string;
  home_team_name?: string | null;
  home_team_name_zh?: string | null;
  away_team_name?: string | null;
  away_team_name_zh?: string | null;
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
  odds_home?: number | null;
  odds_draw?: number | null;
  odds_away?: number | null;
  bookmaker?: string | null;
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

function mean(nums: number[]) {
  if (!nums.length) return 0;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function clamp(x: number, a: number, b: number) {
  return Math.max(a, Math.min(b, x));
}

function isMissingColumnError(message?: string | null) {
  return /column .* does not exist/i.test(String(message || ""));
}

async function loadPersistedPredictionsByDate(sb: ReturnType<typeof supabaseAdmin>, requestedDate: string) {
  const sportteryFixturesResp = await sb
    .from("fixtures")
    .select(
      "fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name,sporttery_match_number"
    )
    .eq("sporttery_sales_day", requestedDate)
    .order("sporttery_match_number", { ascending: true })
    .order("utc_date", { ascending: true });

  if (sportteryFixturesResp.error && !isMissingColumnError(sportteryFixturesResp.error.message)) {
    throw new Error(sportteryFixturesResp.error.message);
  }

  let fixtures = ((sportteryFixturesResp.data || []) as FixtureListRow[]) || [];
  let forceOnSale = fixtures.length > 0;

  if (fixtures.length === 0) {
    const from = new Date(`${requestedDate}T00:00:00.000Z`).toISOString();
    const to = new Date(new Date(`${requestedDate}T00:00:00.000Z`).getTime() + 24 * 3600 * 1000).toISOString();
    const fallback = await sb
      .from("fixtures")
      .select("fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name")
      .gte("utc_date", from)
      .lt("utc_date", to)
      .order("utc_date", { ascending: true });
    if (fallback.error) throw new Error(fallback.error.message);
    fixtures = (fallback.data || []) as FixtureListRow[];
    forceOnSale = false;
  }

  if (fixtures.length === 0) return [];

  const translatedTeams = await translateTeamNamesWithCache(fixtures.flatMap((f) => [f.home_team_name, f.away_team_name]));
  const fixtureIds = fixtures.map((f) => f.fixture_id);
  const predResp = await sb
    .from("fixture_predictions")
    .select(
      "fixture_id,p_home,p_draw,p_away,confidence,lambda_home,lambda_away,p_over_2_5,p_under_2_5,p_btts_yes,p_btts_no,odds_home,odds_draw,odds_away,bookmaker,ev_home,ev_draw,ev_away,kelly_home,kelly_draw,kelly_away,sporttery_handicap"
    )
    .in("fixture_id", fixtureIds);

  if (predResp.error && !isMissingColumnError(predResp.error.message)) {
    throw new Error(predResp.error.message);
  }
  if (predResp.error && isMissingColumnError(predResp.error.message)) {
    const fallbackPredResp = await sb
      .from("fixture_predictions")
      .select(
        "fixture_id,p_home,p_draw,p_away,confidence,lambda_home,lambda_away,p_over_2_5,p_under_2_5,p_btts_yes,p_btts_no,odds_home,odds_draw,odds_away,bookmaker,ev_home,ev_draw,ev_away,kelly_home,kelly_draw,kelly_away"
      )
      .in("fixture_id", fixtureIds);
    if (fallbackPredResp.error) throw new Error(fallbackPredResp.error.message);
    predResp.data = fallbackPredResp.data as any;
  }

  const predMap = new Map<number, any>(((predResp.data || []) as any[]).map((row) => [Number(row.fixture_id), row]));

  return fixtures
    .map((f) => {
      const pred = predMap.get(f.fixture_id);
      if (!pred) return null;
      return {
        fixture_id: f.fixture_id,
        competition_code: f.competition_code,
        competition_name: f.competition_name ?? null,
        competition_name_zh: competitionNameZh(f.competition_code, f.competition_name),
        utc_date: f.utc_date ?? null,
        kickoff_time_zh: formatLocalTimeFromUtc(f.utc_date, "Asia/Shanghai"),
        status: f.status ?? null,
        status_zh: forceOnSale ? "在售" : statusZh(f.status),
        home_team_name: f.home_team_name ?? null,
        home_team_name_zh:
          teamNameZhMaybe(f.home_team_name) || translatedTeams[(f.home_team_name || "").trim()] || f.home_team_name,
        away_team_name: f.away_team_name ?? null,
        away_team_name_zh:
          teamNameZhMaybe(f.away_team_name) || translatedTeams[(f.away_team_name || "").trim()] || f.away_team_name,
        sporttery_handicap: typeof pred.sporttery_handicap === "number" ? pred.sporttery_handicap : null,
        p_home: Number(pred.p_home || 0),
        p_draw: Number(pred.p_draw || 0),
        p_away: Number(pred.p_away || 0),
        confidence: Number(pred.confidence || 0),
        lambda_home: Number(pred.lambda_home || 0),
        lambda_away: Number(pred.lambda_away || 0),
        p_over_2_5: typeof pred.p_over_2_5 === "number" ? pred.p_over_2_5 : undefined,
        p_under_2_5: typeof pred.p_under_2_5 === "number" ? pred.p_under_2_5 : undefined,
        p_btts_yes: typeof pred.p_btts_yes === "number" ? pred.p_btts_yes : undefined,
        p_btts_no: typeof pred.p_btts_no === "number" ? pred.p_btts_no : undefined,
        odds_home: typeof pred.odds_home === "number" ? pred.odds_home : undefined,
        odds_draw: typeof pred.odds_draw === "number" ? pred.odds_draw : undefined,
        odds_away: typeof pred.odds_away === "number" ? pred.odds_away : undefined,
        bookmaker: pred.bookmaker || undefined,
        ev_home: typeof pred.ev_home === "number" ? pred.ev_home : undefined,
        ev_draw: typeof pred.ev_draw === "number" ? pred.ev_draw : undefined,
        ev_away: typeof pred.ev_away === "number" ? pred.ev_away : undefined,
        kelly_home: typeof pred.kelly_home === "number" ? pred.kelly_home : undefined,
        kelly_draw: typeof pred.kelly_draw === "number" ? pred.kelly_draw : undefined,
        kelly_away: typeof pred.kelly_away === "number" ? pred.kelly_away : undefined,
        factors: [],
      } satisfies PredictionOut;
    })
    .filter(Boolean) as PredictionOut[];
}

function inferLambdasFromTarget(target: { p_home: number; p_draw: number; p_away: number }) {
  // 用一个粗粒度网格搜索，找到能近似复现胜平负概率的 λH/λA，
  // 让 predictions 页仍然可以展示 Top 比分 / 大小球等衍生信息。
  let best = { lambdaHome: 1.35, lambdaAway: 1.05, loss: Number.POSITIVE_INFINITY };
  const step = 0.1;
  for (let lh = 0.3; lh <= 3.5; lh += step) {
    for (let la = 0.3; la <= 3.5; la += step) {
      const p = winDrawLoseFromLambdas(lh, la, 8);
      const loss =
        Math.pow(p.p_home - target.p_home, 2) +
        Math.pow(p.p_draw - target.p_draw, 2) +
        Math.pow(p.p_away - target.p_away, 2);
      if (loss < best.loss) best = { lambdaHome: lh, lambdaAway: la, loss };
    }
  }
  return { lambdaHome: best.lambdaHome, lambdaAway: best.lambdaAway };
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
  return (data || []) as RecentFinishedMatchRow[];
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
  const rows = (data || []) as LeagueScoreRow[];
  const homeGoals = rows.map((r) => r.home_score).filter((x): x is number => typeof x === "number");
  const awayGoals = rows.map((r) => r.away_score).filter((x): x is number => typeof x === "number");
  return {
    avgHome: mean(homeGoals) || 1.35,
    avgAway: mean(awayGoals) || 1.05,
    sample: Math.min(homeGoals.length, awayGoals.length),
  };
}

function teamStats(matches: RecentFinishedMatchRow[], teamId: number) {
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
  const requestedDate = body.date;
  const { sb: adminSb, response } = requireSupabaseAdmin();
  if (!adminSb) return response;

  async function buildSportteryPredictionsBySalesDay(salesDay: string, onlyIds?: Set<number>) {
    const sportteryRows = await loadSportteryFixturesBySalesDay(salesDay);
    if (sportteryRows.length === 0) return [] as PredictionOut[];

    const seeds = await loadSportteryPredictionSeedsBySalesDay(salesDay);
    const seedMap = new Map(seeds.map((s) => [s.fixture_id, s]));
    const translatedTeams = await translateTeamNamesWithCache(
      sportteryRows.flatMap((f) => [f.home_team_name, f.away_team_name]),
    );

    const predictions: PredictionOut[] = [];
    for (const f of sportteryRows) {
      if (onlyIds && !onlyIds.has(f.fixture_id)) continue;
      const seed = seedMap.get(f.fixture_id);
      if (!seed) continue; // 没有分析结果则认为“未预测”

      const { lambdaHome, lambdaAway } = inferLambdasFromTarget({
        p_home: seed.p_home,
        p_draw: seed.p_draw,
        p_away: seed.p_away,
      });
      const scoreTop = topScorelines(lambdaHome, lambdaAway, 6, 5);
      const totals = totalsProbs(lambdaHome, lambdaAway, 8);

      const entropy = -(
        seed.p_home * Math.log(seed.p_home + 1e-9) +
        seed.p_draw * Math.log(seed.p_draw + 1e-9) +
        seed.p_away * Math.log(seed.p_away + 1e-9)
      );
      const confidence = clamp((1.1 - entropy / 1.1) * 0.85, 0.08, 0.92);

      predictions.push({
        fixture_id: f.fixture_id,
        competition_code: f.competition_code,
        competition_name: f.competition_name ?? null,
        competition_name_zh: competitionNameZh(f.competition_code, f.competition_name),
        utc_date: f.utc_date ?? null,
        kickoff_time_zh: formatLocalTimeFromUtc(f.utc_date, "Asia/Shanghai"),
        status: f.status ?? null,
        status_zh: "在售",
        home_team_name: f.home_team_name ?? null,
        home_team_name_zh:
          teamNameZhMaybe(f.home_team_name) ||
          translatedTeams[(f.home_team_name || "").trim()] ||
          f.home_team_name,
        away_team_name: f.away_team_name ?? null,
        away_team_name_zh:
          teamNameZhMaybe(f.away_team_name) ||
          translatedTeams[(f.away_team_name || "").trim()] ||
          f.away_team_name,
        sporttery_handicap: seed.handicap,
        p_home: seed.p_home,
        p_draw: seed.p_draw,
        p_away: seed.p_away,
        confidence,
        lambda_home: lambdaHome,
        lambda_away: lambdaAway,
        scorelines_top: scoreTop,
        ...totals,
        factors: seed.factors,
        total_goals_suggestion: seed.raw.total_goals_suggestion || undefined,
        correct_score_suggestion: seed.raw.correct_score_suggestion || undefined,
        risk_note: seed.raw.market_signal_note || undefined,
      });
    }
    return predictions;
  }

  // 1) date 模式：优先走体彩产物
  if (requestedDate) {
    const persisted = await loadPersistedPredictionsByDate(adminSb, requestedDate);
    if (persisted.length > 0) {
      return NextResponse.json({ count: persisted.length, predictions: persisted });
    }
    const sportteryRows = await loadSportteryFixturesBySalesDay(requestedDate);
    if (sportteryRows.length > 0) {
      const preds = await buildSportteryPredictionsBySalesDay(requestedDate);
      return NextResponse.json({ count: preds.length, predictions: preds });
    }
  }

  // 2) fixture_ids 模式：支持混合（体彩 synthetic fixture_id + Supabase fixtures）
  if (body.fixture_ids?.length) {
    const sportteryIds = body.fixture_ids.filter((id) => parseSportteryFixtureId(id));
    const supabaseIds = body.fixture_ids.filter((id) => !parseSportteryFixtureId(id));

    const output: PredictionOut[] = [];

    if (sportteryIds.length > 0) {
      const byDay = new Map<string, Set<number>>();
      for (const id of sportteryIds) {
        const parsed = parseSportteryFixtureId(id);
        if (!parsed) continue;
        const set = byDay.get(parsed.salesDay) || new Set<number>();
        set.add(id);
        byDay.set(parsed.salesDay, set);
      }
      for (const [salesDay, onlyIds] of byDay.entries()) {
        const preds = await buildSportteryPredictionsBySalesDay(salesDay, onlyIds);
        output.push(...preds);
      }
    }

    if (supabaseIds.length === 0) {
      return NextResponse.json({ count: output.length, predictions: output });
    }

    const { data, error } = await adminSb
      .from("fixtures")
      .select("fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name")
      .in("fixture_id", supabaseIds);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    const fixtures = (data || []) as FixtureListRow[];

    const translatedTeams = await translateTeamNamesWithCache(
      fixtures.flatMap((f) => [f.home_team_name, f.away_team_name]),
    );

    const fixtureIds = fixtures.map((f) => f.fixture_id);
    const oddsMap = new Map<number, { odds_home: number | null; odds_draw: number | null; odds_away: number | null }>();
    if (fixtureIds.length) {
      const { data: oddsRows } = await adminSb
        .from("odds")
        .select("fixture_id,odds_home,odds_draw,odds_away")
        .in("fixture_id", fixtureIds);
      for (const r of (oddsRows || []) as OddsRow[]) {
        oddsMap.set(r.fixture_id, { odds_home: r.odds_home, odds_draw: r.odds_draw, odds_away: r.odds_away });
      }
    }

    for (const f of fixtures) {
      const competitionCode = f.competition_code || "";
      const homeId = f.home_team_id;
      const awayId = f.away_team_id;
      if (!competitionCode || !homeId || !awayId) continue;

      const leagueAvg = await fetchLeagueAverages(adminSb, competitionCode);
      const homeRecent = await fetchRecentFinishedMatches(adminSb, competitionCode, homeId, 20);
      const awayRecent = await fetchRecentFinishedMatches(adminSb, competitionCode, awayId, 20);

      const home = teamStats(homeRecent, homeId);
      const away = teamStats(awayRecent, awayId);

      const homeAttack = home.n >= 5 ? clamp((home.gfAvg || leagueAvg.avgHome) / leagueAvg.avgHome, 0.6, 1.6) : 1.0;
      const homeDef = home.n >= 5 ? clamp((home.gaAvg || leagueAvg.avgAway) / leagueAvg.avgAway, 0.6, 1.6) : 1.0;
      const awayAttack = away.n >= 5 ? clamp((away.gfAvg || leagueAvg.avgAway) / leagueAvg.avgAway, 0.6, 1.6) : 1.0;
      const awayDef = away.n >= 5 ? clamp((away.gaAvg || leagueAvg.avgHome) / leagueAvg.avgHome, 0.6, 1.6) : 1.0;

      const lambdaHome = clamp(leagueAvg.avgHome * homeAttack * awayDef, 0.2, 3.5);
      const lambdaAway = clamp(leagueAvg.avgAway * awayAttack * homeDef, 0.2, 3.5);

      const probs = winDrawLoseFromLambdas(lambdaHome, lambdaAway, 8);
      const scoreTop = topScorelines(lambdaHome, lambdaAway, 6, 5);
      const totals = totalsProbs(lambdaHome, lambdaAway, 8);

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
        home_team_name_zh:
          teamNameZhMaybe(f.home_team_name) || translatedTeams[(f.home_team_name || "").trim()] || f.home_team_name,
        away_team_name: f.away_team_name ?? null,
        away_team_name_zh:
          teamNameZhMaybe(f.away_team_name) || translatedTeams[(f.away_team_name || "").trim()] || f.away_team_name,
        p_home: probs.p_home,
        p_draw: probs.p_draw,
        p_away: probs.p_away,
        confidence,
        lambda_home: lambdaHome,
        lambda_away: lambdaAway,
        scorelines_top: scoreTop,
        ...totals,
        factors,
      };

      const o = oddsMap.get(f.fixture_id);
      if (o && (o.odds_home || o.odds_draw || o.odds_away)) {
        const ek = evAndKelly({ p_home: probs.p_home, p_draw: probs.p_draw, p_away: probs.p_away }, o, 0.25);
        output.push({ ...base, ...ek });
      } else {
        output.push(base);
      }
    }

    return NextResponse.json({ count: output.length, predictions: output });
  }

  // 3) Supabase 传统 date 模式
  if (!requestedDate) {
    return NextResponse.json({ error: "missing date or fixture_ids" }, { status: 400 });
  }

  let fixtures: FixtureListRow[] = [];
  const from = new Date(`${requestedDate}T00:00:00.000Z`).toISOString();
  const to = new Date(new Date(`${requestedDate}T00:00:00.000Z`).getTime() + 24 * 3600 * 1000).toISOString();
  const { data, error } = await adminSb
    .from("fixtures")
    .select("fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name")
    .gte("utc_date", from)
    .lt("utc_date", to)
    .order("utc_date", { ascending: true });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  fixtures = (data || []) as FixtureListRow[];

  const predictions: PredictionOut[] = [];

  const translatedTeams = await translateTeamNamesWithCache(
    fixtures.flatMap((f) => [f.home_team_name, f.away_team_name]),
  );

  const fixtureIds = fixtures.map((f) => f.fixture_id);
  const oddsMap = new Map<number, { odds_home: number | null; odds_draw: number | null; odds_away: number | null }>();
  if (fixtureIds.length) {
    const { data: oddsRows } = await adminSb.from("odds").select("fixture_id,odds_home,odds_draw,odds_away").in("fixture_id", fixtureIds);
    for (const r of (oddsRows || []) as OddsRow[]) {
      oddsMap.set(r.fixture_id, { odds_home: r.odds_home, odds_draw: r.odds_draw, odds_away: r.odds_away });
    }
  }

  for (const f of fixtures) {
    const competitionCode = f.competition_code || "";
    const homeId = f.home_team_id;
    const awayId = f.away_team_id;
    if (!competitionCode || !homeId || !awayId) continue;

    const leagueAvg = await fetchLeagueAverages(adminSb, competitionCode);
    const homeRecent = await fetchRecentFinishedMatches(adminSb, competitionCode, homeId, 20);
    const awayRecent = await fetchRecentFinishedMatches(adminSb, competitionCode, awayId, 20);

    const home = teamStats(homeRecent, homeId);
    const away = teamStats(awayRecent, awayId);

    const homeAttack = home.n >= 5 ? clamp((home.gfAvg || leagueAvg.avgHome) / leagueAvg.avgHome, 0.6, 1.6) : 1.0;
    const homeDef = home.n >= 5 ? clamp((home.gaAvg || leagueAvg.avgAway) / leagueAvg.avgAway, 0.6, 1.6) : 1.0;
    const awayAttack = away.n >= 5 ? clamp((away.gfAvg || leagueAvg.avgAway) / leagueAvg.avgAway, 0.6, 1.6) : 1.0;
    const awayDef = away.n >= 5 ? clamp((away.gaAvg || leagueAvg.avgHome) / leagueAvg.avgHome, 0.6, 1.6) : 1.0;

    const lambdaHome = clamp(leagueAvg.avgHome * homeAttack * awayDef, 0.2, 3.5);
    const lambdaAway = clamp(leagueAvg.avgAway * awayAttack * homeDef, 0.2, 3.5);

    const probs = winDrawLoseFromLambdas(lambdaHome, lambdaAway, 8);
    const scoreTop = topScorelines(lambdaHome, lambdaAway, 6, 5);
    const totals = totalsProbs(lambdaHome, lambdaAway, 8);

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
      home_team_name_zh:
        teamNameZhMaybe(f.home_team_name) || translatedTeams[(f.home_team_name || "").trim()] || f.home_team_name,
      away_team_name: f.away_team_name ?? null,
      away_team_name_zh:
        teamNameZhMaybe(f.away_team_name) || translatedTeams[(f.away_team_name || "").trim()] || f.away_team_name,
      p_home: probs.p_home,
      p_draw: probs.p_draw,
      p_away: probs.p_away,
      confidence,
      lambda_home: lambdaHome,
      lambda_away: lambdaAway,
      scorelines_top: scoreTop,
      ...totals,
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
