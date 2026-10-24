import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
type OddsStatusRow = {
  fixture_id: number;
  odds_home: number | null;
  odds_draw: number | null;
  odds_away: number | null;
  bookmaker: string | null;
  collected_at: string | null;
  updated_at: string | null;
};

type PredictionOddsRow = {
  fixture_id: number;
  odds_home: number | null;
  odds_draw: number | null;
  odds_away: number | null;
  bookmaker: string | null;
  generated_at: string | null;
  as_of_date: string | null;
  model_version: string | null;
  p_home?: number | null;
  p_draw?: number | null;
  p_away?: number | null;
  prediction_source?: string | null;
};

type FixtureOddsDbRow = {
  fixture_id: number;
  competition_code: string | null;
  competition_name: string | null;
  utc_date: string | null;
  status: string | null;
  home_team_name: string | null;
  away_team_name: string | null;
  sporttery_match_number?: string | null;
};

function isMissingColumnError(message?: string | null) {
  return /column .* does not exist/i.test(String(message || ""));
}

function salesDayUtcRange(requestedDate: string) {
  const from = new Date(`${requestedDate}T00:00:00.000Z`).toISOString();
  const to = new Date(new Date(`${requestedDate}T00:00:00.000Z`).getTime() + 24 * 3600 * 1000).toISOString();
  return { from, to };
}

// 赔率三向的派生指标：隐含概率（含抽水）、返还率、去水概率
function computeOddsMetrics(home?: number | null, draw?: number | null, away?: number | null) {
  const h = typeof home === "number" && home > 1 ? home : null;
  const d = typeof draw === "number" && draw > 1 ? draw : null;
  const a = typeof away === "number" && away > 1 ? away : null;
  if (!h || !d || !a) return null;
  const invHome = 1 / h;
  const invDraw = 1 / d;
  const invAway = 1 / a;
  const invSum = invHome + invDraw + invAway;
  const payoutRate = 1 / invSum;
  return {
    implied_home: invHome,
    implied_draw: invDraw,
    implied_away: invAway,
    payout_rate: payoutRate,
    fair_home: invHome * payoutRate,
    fair_draw: invDraw * payoutRate,
    fair_away: invAway * payoutRate,
  };
}

// 凯利指数（模型口径）：模型概率 × 赔率，>1 表示该方向存在正期望
function computeKellyIndexes(
  odds: { home?: number | null; draw?: number | null; away?: number | null },
  model: { p_home?: number | null; p_draw?: number | null; p_away?: number | null },
) {
  const pick = (oddsValue: number | null | undefined, pValue: number | null | undefined) =>
    typeof oddsValue === "number" && oddsValue > 1 && typeof pValue === "number" && pValue > 0 ? pValue * oddsValue : null;
  const home = pick(odds.home, model.p_home);
  const draw = pick(odds.draw, model.p_draw);
  const away = pick(odds.away, model.p_away);
  const candidates: Array<{ side: "home" | "draw" | "away"; label: string; value: number }> = [];
  if (home != null) candidates.push({ side: "home", label: "主胜", value: home });
  if (draw != null) candidates.push({ side: "draw", label: "平局", value: draw });
  if (away != null) candidates.push({ side: "away", label: "客胜", value: away });
  const best = candidates.sort((x, y) => y.value - x.value)[0] || null;
  return {
    kelly_home: home,
    kelly_draw: draw,
    kelly_away: away,
    value_side: best && best.value > 1 ? best.label : null,
    value_edge: best && best.value > 1 ? best.value - 1 : null,
  };
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
        "fixture_id,competition_code,competition_name,utc_date,status,home_team_name,away_team_name,sporttery_match_number"
      )
      .eq("sporttery_sales_day", requestedDate)
      .order("sporttery_match_number", { ascending: true })
      .order("utc_date", { ascending: true });

    let fixtureRows: FixtureOddsDbRow[] = [];
    if (primaryFixturesResp.error && isMissingColumnError(primaryFixturesResp.error.message)) {
      const { from, to } = salesDayUtcRange(requestedDate);
      const fallbackResp = await sb
        .from("fixtures")
        .select("fixture_id,competition_code,competition_name,utc_date,status,home_team_name,away_team_name")
        .gte("utc_date", from)
        .lt("utc_date", to)
        .order("utc_date", { ascending: true });
      if (fallbackResp.error) {
        return NextResponse.json({ error: fallbackResp.error.message }, { status: 500 });
      }
      fixtureRows = (fallbackResp.data || []) as FixtureOddsDbRow[];
    } else {
      if (primaryFixturesResp.error) {
        return NextResponse.json({ error: primaryFixturesResp.error.message }, { status: 500 });
      }
      fixtureRows = (primaryFixturesResp.data || []) as FixtureOddsDbRow[];
    }

    const fixtures = fixtureRows.map((row) => ({
      ...row,
      sporttery_match_number: row.sporttery_match_number ?? null,
    }));
    const fixtureIds = fixtures.map((item) => item.fixture_id);

    const [oddsResp, predictionResp] = await Promise.all([
      fixtureIds.length > 0
        ? sb.from("odds").select("fixture_id,odds_home,odds_draw,odds_away,bookmaker,collected_at,updated_at").in("fixture_id", fixtureIds)
        : Promise.resolve({ data: [], error: null }),
      fixtureIds.length > 0
        ? sb
            .from("fixture_predictions")
            .select("fixture_id,odds_home,odds_draw,odds_away,bookmaker,generated_at,as_of_date,model_version,p_home,p_draw,p_away,prediction_source")
            .in("fixture_id", fixtureIds)
        : Promise.resolve({ data: [], error: null }),
    ]);

    if (oddsResp.error && !isMissingColumnError(oddsResp.error.message)) {
      return NextResponse.json({ error: oddsResp.error.message }, { status: 500 });
    }
    if (predictionResp.error) {
      if (/prediction_source/.test(predictionResp.error.message || "")) {
        const fallbackPredictionResp =
          fixtureIds.length > 0
            ? await sb
                .from("fixture_predictions")
                .select("fixture_id,odds_home,odds_draw,odds_away,bookmaker,generated_at,as_of_date,model_version,p_home,p_draw,p_away")
                .in("fixture_id", fixtureIds)
            : { data: [], error: null };
        if (fallbackPredictionResp.error && !isMissingColumnError(fallbackPredictionResp.error.message)) {
          return NextResponse.json({ error: fallbackPredictionResp.error.message }, { status: 500 });
        }
        predictionResp.data = fallbackPredictionResp.data as any;
        predictionResp.error = fallbackPredictionResp.error as any;
      } else if (!isMissingColumnError(predictionResp.error.message)) {
        return NextResponse.json({ error: predictionResp.error.message }, { status: 500 });
      } else {
        predictionResp.data = [] as any;
        predictionResp.error = null as any;
      }
    }

    const oddsMap = new Map<number, OddsStatusRow>();
    for (const row of (oddsResp.data || []) as OddsStatusRow[]) {
      oddsMap.set(row.fixture_id, row);
    }

    const predictionMap = new Map<number, PredictionOddsRow>();
    for (const row of (predictionResp.data || []) as PredictionOddsRow[]) {
      predictionMap.set(row.fixture_id, row);
    }

    const rows = fixtures.map((fixture) => {
      const odds = oddsMap.get(fixture.fixture_id);
      const prediction = predictionMap.get(fixture.fixture_id);
      const hasDirectOdds = Boolean(odds && (odds.odds_home || odds.odds_draw || odds.odds_away));
      const hasPredictionSnapshotOdds = Boolean(
        prediction && (prediction.odds_home || prediction.odds_draw || prediction.odds_away)
      );
      const statusMode = hasDirectOdds
        ? hasPredictionSnapshotOdds
          ? "both"
          : "direct_only"
        : hasPredictionSnapshotOdds
          ? "snapshot_only"
          : "missing";
      const missingReason =
        statusMode === "missing"
          ? "直接赔率与预测快照都缺失"
          : statusMode === "snapshot_only"
            ? "尚未写入 odds 表"
            : statusMode === "direct_only"
              ? "预测快照未保留赔率"
              : null;

      // 指标计算口径：优先直接赔率，缺失时退回预测快照赔率
      const primaryOdds = hasDirectOdds
        ? { home: odds?.odds_home, draw: odds?.odds_draw, away: odds?.odds_away }
        : { home: prediction?.odds_home, draw: prediction?.odds_draw, away: prediction?.odds_away };
      const primarySource = hasDirectOdds ? "direct" : hasPredictionSnapshotOdds ? "snapshot" : null;
      const metrics = primarySource ? computeOddsMetrics(primaryOdds.home, primaryOdds.draw, primaryOdds.away) : null;
      const kelly = primarySource
        ? computeKellyIndexes(primaryOdds, {
            p_home: prediction?.p_home ?? null,
            p_draw: prediction?.p_draw ?? null,
            p_away: prediction?.p_away ?? null,
          })
        : { kelly_home: null, kelly_draw: null, kelly_away: null, value_side: null, value_edge: null };

      return {
        fixture_id: fixture.fixture_id,
        sporttery_match_number: fixture.sporttery_match_number ?? null,
        competition_name: fixture.competition_name ?? null,
        utc_date: fixture.utc_date ?? null,
        home_team_name: fixture.home_team_name ?? null,
        away_team_name: fixture.away_team_name ?? null,
        bookmaker: odds?.bookmaker ?? null,
        collected_at: odds?.collected_at ?? null,
        updated_at: odds?.updated_at ?? null,
        odds_home: odds?.odds_home ?? null,
        odds_draw: odds?.odds_draw ?? null,
        odds_away: odds?.odds_away ?? null,
        prediction_bookmaker: prediction?.bookmaker ?? null,
        prediction_generated_at: prediction?.generated_at ?? null,
        prediction_as_of_date: prediction?.as_of_date ?? null,
        prediction_model_version: prediction?.model_version ?? null,
        prediction_source: prediction?.prediction_source ?? null,
        prediction_odds_home: prediction?.odds_home ?? null,
        prediction_odds_draw: prediction?.odds_draw ?? null,
        prediction_odds_away: prediction?.odds_away ?? null,
        has_direct_odds: hasDirectOdds,
        has_prediction_snapshot_odds: hasPredictionSnapshotOdds,
        status_mode: statusMode,
        missing_reason: missingReason,
        metrics_source: primarySource,
        implied_home: metrics?.implied_home ?? null,
        implied_draw: metrics?.implied_draw ?? null,
        implied_away: metrics?.implied_away ?? null,
        payout_rate: metrics?.payout_rate ?? null,
        fair_home: metrics?.fair_home ?? null,
        fair_draw: metrics?.fair_draw ?? null,
        fair_away: metrics?.fair_away ?? null,
        model_p_home: prediction?.p_home ?? null,
        model_p_draw: prediction?.p_draw ?? null,
        model_p_away: prediction?.p_away ?? null,
        kelly_home: kelly.kelly_home,
        kelly_draw: kelly.kelly_draw,
        kelly_away: kelly.kelly_away,
        value_side: kelly.value_side,
        value_edge: kelly.value_edge,
      };
    });

    const sourceCountMap = new Map<string, number>();
    for (const row of rows) {
      if (!row.bookmaker) continue;
      sourceCountMap.set(row.bookmaker, (sourceCountMap.get(row.bookmaker) || 0) + 1);
    }

    const missingCountMap = new Map<string, number>();
    for (const row of rows) {
      if (!row.missing_reason) continue;
      missingCountMap.set(row.missing_reason, (missingCountMap.get(row.missing_reason) || 0) + 1);
    }

    const latestDirectCollectedAt =
      rows
        .map((row) => row.collected_at)
        .filter((value): value is string => Boolean(value))
        .sort((a, b) => b.localeCompare(a))[0] || null;
    const latestSnapshotGeneratedAt =
      rows
        .map((row) => row.prediction_generated_at)
        .filter((value): value is string => Boolean(value))
        .sort((a, b) => b.localeCompare(a))[0] || null;

    return NextResponse.json({
      sales_day: requestedDate,
      fixture_count: rows.length,
      direct_odds_count: rows.filter((row) => row.has_direct_odds).length,
      prediction_snapshot_odds_count: rows.filter((row) => row.has_prediction_snapshot_odds).length,
      value_side_count: rows.filter((row) => row.value_side).length,
      avg_payout_rate:
        rows.filter((row) => row.payout_rate != null).length > 0
          ? rows.reduce((sum, row) => sum + (row.payout_rate || 0), 0) /
            rows.filter((row) => row.payout_rate != null).length
          : null,
      latest_direct_collected_at: latestDirectCollectedAt,
      latest_snapshot_generated_at: latestSnapshotGeneratedAt,
      source_summary: [...sourceCountMap.entries()]
        .map(([bookmaker, count]) => ({ bookmaker, count }))
        .sort((a, b) => b.count - a.count),
      missing_summary: [...missingCountMap.entries()]
        .map(([reason, count]) => ({ reason, count }))
        .sort((a, b) => b.count - a.count),
      rows,
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
