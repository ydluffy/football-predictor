import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { localArtifactsEnabled } from "@/lib/localArtifacts";
import { hasConfirmedEmptySportteryScan, loadSportteryFixturesBySalesDay, parseSportteryFixtureId } from "@/lib/sportteryFixtures";
import { loadSportteryPredictionSeedsBySalesDay } from "@/lib/sportteryPredictions";
import { verifiedArtifactUpsert } from "@/lib/verifiedArtifactUpsert";

/** Controller-only export of frozen observations. Never invokes the prediction engine. */
export async function POST(req: Request) {
  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;
  if (!localArtifactsEnabled()) return NextResponse.json({ error: "local_artifacts_disabled" }, { status: 503 });
  try {
    const { date } = await req.json();
    if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return NextResponse.json({ error: "invalid sales date" }, { status: 400 });
    }
    const fixtures = await loadSportteryFixturesBySalesDay(date);
    if (!fixtures.length) {
      if (await hasConfirmedEmptySportteryScan(date)) return NextResponse.json({ verified: true, no_matches: true, persisted_fixtures: 0, snapshotted: 0 });
      return NextResponse.json({ error: "missing confirmed snapshot", verified: false }, { status: 409 });
    }
    const fixtureRows = fixtures.map((f) => {
      // Do not reset FINISHED status or erase previously imported scores during a retry.
      const { status: _status, home_score: _home, away_score: _away, ...identity } = f;
      void _status; void _home; void _away;
      return { ...identity, data_source: "sporttery", sporttery_sales_day: date,
        sporttery_match_number: parseSportteryFixtureId(f.fixture_id)?.matchNumber ?? null };
    });
    const fixtureResult = await verifiedArtifactUpsert(sb, "fixtures", fixtureRows, "fixture_id");
    if (fixtureResult.error) return NextResponse.json({ error: fixtureResult.error.message }, { status: 500 });
    const seeds = await loadSportteryPredictionSeedsBySalesDay(date);
    const ids = new Set(fixtures.map((f) => f.fixture_id));
    const predictions = seeds.filter((s) => ids.has(s.fixture_id)).map((s) => {
      const raw = s.raw as unknown as Record<string, string>;
      const odd = (key: string, favorite: boolean) => {
        const value = Number(raw[`spf_odds_${key}`] || (favorite ? raw.favorite_odds : ""));
        return Number.isFinite(value) && value > 1 ? value : null;
      };
      return {
      fixture_id: s.fixture_id, as_of_date: date, generated_at: s.source_captured_at,
      model_version: "frozen_sporttery_market_v1", prediction_source: "sporttery_local_artifacts",
      p_home: s.p_home, p_draw: s.p_draw, p_away: s.p_away,
      sporttery_handicap: s.handicap,
      odds_home: odd("home", raw.favorite_label.includes("主")),
      odds_draw: odd("draw", raw.favorite_label === "平"),
      odds_away: odd("away", raw.favorite_label.includes("客")), bookmaker: "sporttery_frozen_artifacts",
      // No inferred goal model, EV, stake or new recommendation is created by this exporter.
      confidence: null, lambda_home: null, lambda_away: null,
      p_over_2_5: null, p_under_2_5: null, p_btts_yes: null, p_btts_no: null,
      ev_home: null, ev_draw: null, ev_away: null, kelly_home: null, kelly_draw: null, kelly_away: null,
    }; });
    const predictionResult = await verifiedArtifactUpsert(sb, "fixture_predictions", predictions, "fixture_id");
    if (predictionResult.error) return NextResponse.json({ error: predictionResult.error.message }, { status: 500 });
    return NextResponse.json({ verified: true, persisted_fixtures: fixtureResult.count,
      snapshotted: predictionResult.count, no_frozen_predictions: !predictions.length });
  } catch {
    return NextResponse.json({ error: "frozen_snapshot_sync_failed" }, { status: 500 });
  }
}
