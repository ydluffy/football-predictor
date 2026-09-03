import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import type { PredictionApiItem } from "@/lib/databaseTypes";
import { loadSportteryFixturesBySalesDay, parseSportteryFixtureId } from "@/lib/sportteryFixtures";

function isMissingColumnError(message?: string | null) {
  const m = String(message || "");
  return /column .* does not exist/i.test(m);
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { date?: string };
  const date = body.date;
  if (!date) return NextResponse.json({ error: "missing date" }, { status: 400 });

  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const predsResp = await fetch(`${new URL(req.url).origin}/api/predictions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date }),
  });
  const predsTxt = await predsResp.text();
  if (!predsResp.ok) return NextResponse.json({ error: predsTxt || `HTTP ${predsResp.status}` }, { status: 500 });
  const predsJson = JSON.parse(predsTxt) as { predictions?: PredictionApiItem[] };
  const predictions = predsJson.predictions || [];
  if (!predictions.length) {
    return NextResponse.json({ date, snapshotted: 0 });
  }

  // 若本次预测来源包含体彩合成 fixture_id，则顺手把体彩赛程落库（用于历史查询/复盘）
  // 注意：为了兼容“数据库还没执行新迁移”的情况，写库时会做一次降级重试。
  const hasSportteryFixture = predictions.some((p) => Boolean(parseSportteryFixtureId(p.fixture_id)));
  if (hasSportteryFixture) {
    const fixtures = await loadSportteryFixturesBySalesDay(date);
    if (fixtures.length > 0) {
      const extendedFixtures = fixtures.map((f) => {
        const parsed = parseSportteryFixtureId(f.fixture_id);
        return {
          ...f,
          data_source: "sporttery",
          sporttery_sales_day: date,
          sporttery_match_number: parsed?.matchNumber ?? null,
        };
      });

      const { error: fxErr } = await sb.from("fixtures").upsert(extendedFixtures as any, { onConflict: "fixture_id" });
      if (fxErr && isMissingColumnError(fxErr.message)) {
        // 迁移未执行：降级为只写旧字段
        const { error: fxErr2 } = await sb.from("fixtures").upsert(fixtures as any, { onConflict: "fixture_id" });
        if (fxErr2) return NextResponse.json({ error: fxErr2.message }, { status: 500 });
      } else if (fxErr) {
        return NextResponse.json({ error: fxErr.message }, { status: 500 });
      }
    }
  }

  const upserts = predictions.map((p) => ({
    fixture_id: p.fixture_id,
    model_version: "poisson_v1",
    as_of_date: date,
    generated_at: new Date().toISOString(),
    p_home: p.p_home,
    p_draw: p.p_draw,
    p_away: p.p_away,
    confidence: p.confidence,
    lambda_home: p.lambda_home,
    lambda_away: p.lambda_away,
    p_over_2_5: p.p_over_2_5,
    p_under_2_5: p.p_under_2_5,
    p_btts_yes: p.p_btts_yes,
    p_btts_no: p.p_btts_no,
    odds_home: p.odds_home ?? null,
    odds_draw: p.odds_draw ?? null,
    odds_away: p.odds_away ?? null,
    bookmaker: p.bookmaker ?? null,
    ev_home: p.ev_home ?? null,
    ev_draw: p.ev_draw ?? null,
    ev_away: p.ev_away ?? null,
    kelly_home: p.kelly_home ?? null,
    kelly_draw: p.kelly_draw ?? null,
    kelly_away: p.kelly_away ?? null,
    // 可选扩展字段（若 DB 尚未迁移，会在下面降级重试）
    sporttery_handicap: p.sporttery_handicap ?? null,
    prediction_source: hasSportteryFixture ? "sporttery_local_artifacts" : "supabase_fixtures",
  }));

  const { error } = await sb.from("fixture_predictions").upsert(upserts as any, { onConflict: "fixture_id" });
  if (error && isMissingColumnError(error.message)) {
    // 迁移未执行：降级为只写旧字段（避免因为新列不存在而整体失败）
    const fallbackUpserts = predictions.map((p) => ({
      fixture_id: p.fixture_id,
      model_version: "poisson_v1",
      as_of_date: date,
      generated_at: new Date().toISOString(),
      p_home: p.p_home,
      p_draw: p.p_draw,
      p_away: p.p_away,
      confidence: p.confidence,
      lambda_home: p.lambda_home,
      lambda_away: p.lambda_away,
      p_over_2_5: p.p_over_2_5,
      p_under_2_5: p.p_under_2_5,
      p_btts_yes: p.p_btts_yes,
      p_btts_no: p.p_btts_no,
      odds_home: p.odds_home ?? null,
      odds_draw: p.odds_draw ?? null,
      odds_away: p.odds_away ?? null,
      bookmaker: p.bookmaker ?? null,
      ev_home: p.ev_home ?? null,
      ev_draw: p.ev_draw ?? null,
      ev_away: p.ev_away ?? null,
      kelly_home: p.kelly_home ?? null,
      kelly_draw: p.kelly_draw ?? null,
      kelly_away: p.kelly_away ?? null,
    }));
    const { error: e2 } = await sb.from("fixture_predictions").upsert(fallbackUpserts as any, { onConflict: "fixture_id" });
    if (e2) return NextResponse.json({ error: e2.message }, { status: 500 });
  } else if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ date, snapshotted: upserts.length });
}

