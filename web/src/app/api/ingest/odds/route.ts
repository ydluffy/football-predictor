import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import type { FixtureListRow } from "@/lib/databaseTypes";

type ApiFootballOddsResponse = {
  response?: Array<{
    fixture?: { date?: string | null; id?: number | null };
    teams?: { home?: { name?: string | null }; away?: { name?: string | null } };
    bookmakers?: Array<{
      name?: string | null;
      bets?: Array<{
        name?: string | null;
        values?: Array<{ value?: string | null; odd?: string | null }>;
      }>;
    }>;
  }>;
};

function normalizeName(s?: string | null) {
  return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

export async function POST(req: Request) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get("date"); // YYYY-MM-DD (Asia/Shanghai)
  const bookmakerId = searchParams.get("bookmaker"); // optional, not all plans support filtering by bookmaker
  if (!date) return NextResponse.json({ error: "missing date" }, { status: 400 });

  const apiKey = process.env.API_FOOTBALL_KEY;
  if (!apiKey) return NextResponse.json({ error: "missing API_FOOTBALL_KEY" }, { status: 500 });

  // Load fixtures from our DB for the given date window (Asia/Shanghai -> UTC)
  const sb = supabaseAdmin();
  const fromLocal = new Date(`${date}T00:00:00+08:00`).toISOString();
  const toLocal = new Date(new Date(`${date}T00:00:00+08:00`).getTime() + 24 * 3600 * 1000).toISOString();
  const { data: fixtures, error: fxErr } = await sb
    .from("fixtures")
    .select("fixture_id,home_team_name,away_team_name,utc_date")
    .gte("utc_date", fromLocal)
    .lt("utc_date", toLocal);
  if (fxErr) return NextResponse.json({ error: fxErr.message }, { status: 500 });

  // Fetch odds from API-Football by date; parse 1X2 market (Match Winner)
  const url = new URL("https://v3.football.api-sports.io/odds");
  url.searchParams.set("date", date);
  url.searchParams.set("timezone", "Asia/Shanghai");
  if (bookmakerId) url.searchParams.set("bookmaker", bookmakerId);
  const resp = await fetch(url.toString(), {
    headers: { "x-apisports-key": apiKey, Accept: "application/json" },
  });
  const raw = await resp.text();
  if (!resp.ok) return NextResponse.json({ error: `api-football ${resp.status}: ${raw.slice(0, 800)}` }, { status: resp.status });
  let payload: ApiFootballOddsResponse;
  try {
    payload = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "invalid json from API-Football" }, { status: 502 });
  }

  const fixtureRows = (fixtures || []) as FixtureListRow[];
  const updates: Array<{ fixture_id: number; odds_home: number; odds_draw: number; odds_away: number; bookmaker?: string }> = [];
  const fxNorm = (s?: string | null) => normalizeName(s);

  for (const item of payload.response || []) {
    const homeName = fxNorm(item.teams?.home?.name);
    const awayName = fxNorm(item.teams?.away?.name);
    if (!homeName || !awayName) continue;
    // Find our fixture by fuzzy matching team names
    const candidates = fixtureRows.filter((f) => {
      const h = fxNorm(f.home_team_name);
      const a = fxNorm(f.away_team_name);
      return h && a && (h === homeName || h.includes(homeName) || homeName.includes(h)) && (a === awayName || a.includes(awayName) || awayName.includes(a));
    });
    if (!candidates.length) continue;
    const fx = candidates[0];

    // Parse 1X2 odds from bookmakers
    let best: { H?: number; D?: number; A?: number; bk?: string } = {};
    for (const bk of item.bookmakers || []) {
      for (const bet of bk.bets || []) {
        const bn = (bet.name || "").toLowerCase();
        if (bn.includes("match winner") || bn.includes("1x2") || bn.includes("winner")) {
          const vals = bet.values || [];
          let H: number | undefined, D: number | undefined, A: number | undefined;
          for (const v of vals) {
            const label = (v.value || "").toLowerCase();
            const odd = v.odd ? Number(v.odd) : NaN;
            if (!isFinite(odd) || odd <= 1) continue;
            if (label.includes("home") || label === "1") H = odd;
            else if (label.includes("draw") || label === "x") D = odd;
            else if (label.includes("away") || label === "2") A = odd;
          }
          if (H && D && A) {
            // choose the first full set encountered as "best"
            if (!best.H || !best.D || !best.A) best = { H, D, A, bk: bk.name || undefined };
          }
        }
      }
    }
    if (best.H && best.D && best.A) {
      updates.push({
        fixture_id: fx.fixture_id,
        odds_home: best.H,
        odds_draw: best.D,
        odds_away: best.A,
        bookmaker: best.bk,
      });
    }
  }

  if (!updates.length) {
    return NextResponse.json({ updated: 0, note: "no odds parsed or matched for given date" });
  }
  const { error: upErr } = await sb.from("odds").upsert(updates, { onConflict: "fixture_id" });
  if (upErr) return NextResponse.json({ error: upErr.message }, { status: 500 });
  return NextResponse.json({ updated: updates.length });
}

