import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { date?: string };
  const date = body.date;
  if (!date) return NextResponse.json({ error: "missing date" }, { status: 400 });

  const sb = supabaseAdmin();

  const predsResp = await fetch(`${new URL(req.url).origin}/api/predictions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date }),
  });
  const predsTxt = await predsResp.text();
  if (!predsResp.ok) return NextResponse.json({ error: predsTxt || `HTTP ${predsResp.status}` }, { status: 500 });
  const predsJson = JSON.parse(predsTxt) as { predictions: any[] };
  const predictions = predsJson.predictions || [];
  if (!predictions.length) {
    return NextResponse.json({ date, snapshotted: 0 });
  }

  const upserts = predictions.map((p: any) => ({
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

  const { error } = await sb.from("fixture_predictions").upsert(upserts, { onConflict: "fixture_id" });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ date, snapshotted: upserts.length });
}

