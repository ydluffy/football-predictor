import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as {
      odds: Array<{ fixture_id: number; odds_home: number; odds_draw: number; odds_away: number; bookmaker?: string }>;
    };
    if (!body?.odds?.length) {
      return NextResponse.json({ error: "missing odds[]" }, { status: 400 });
    }
    const sb = supabaseAdmin();
    const { error } = await sb.from("odds").upsert(
      body.odds.map((o) => ({
        fixture_id: o.fixture_id,
        odds_home: o.odds_home,
        odds_draw: o.odds_draw,
        odds_away: o.odds_away,
        bookmaker: o.bookmaker ?? null,
      })),
      { onConflict: "fixture_id" }
    );
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ upserted: body.odds.length });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 400 });
  }
}

