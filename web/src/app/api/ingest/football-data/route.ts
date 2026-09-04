import { NextResponse } from "next/server";
import { fetchMajorLeagueMatches, type FixtureRow } from "@/lib/footballDataOrg";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";

export async function POST(req: Request) {
  const { searchParams } = new URL(req.url);
  const dateFrom = searchParams.get("date_from");
  const dateTo = searchParams.get("date_to");

  if (!dateFrom || !dateTo) {
    return NextResponse.json({ error: "missing date_from/date_to" }, { status: 400 });
  }

  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;
  // Short-circuit: if data already exists in this (local CN) date range, skip upstream calls
  const fromLocal = new Date(`${dateFrom}T00:00:00+08:00`);
  const toLocal = new Date(new Date(`${dateTo}T00:00:00+08:00`).getTime() + 24 * 3600 * 1000);
  const fromUtcIso = fromLocal.toISOString();
  const toUtcIso = toLocal.toISOString();

  const existing = await sb
    .from("fixtures")
    .select("fixture_id", { count: "exact", head: true })
    .gte("utc_date", fromUtcIso)
    .lt("utc_date", toUtcIso);
  if (!existing.error && typeof existing.count === "number" && existing.count > 0) {
    return NextResponse.json({
      date_from: dateFrom,
      date_to: dateTo,
      inserted_or_updated: 0,
      already_present: true,
      note: "fixtures already exist in this date range; skipped upstream fetch",
    });
  }

  let rows: FixtureRow[] = [];
  try {
    rows = await fetchMajorLeagueMatches(dateFrom, dateTo);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const isRateLimit = /429|Too Many Requests/i.test(msg);
    return NextResponse.json(
      {
        error: isRateLimit
          ? "Rate limited by football-data.org (free tier ~10 req/min). Please wait 1–2 minutes and try again."
          : `Upstream fetch failed: ${msg}`,
      },
      { status: isRateLimit ? 429 : 502 }
    );
  }
  const { error } = await sb.from("fixtures").upsert(rows, { onConflict: "fixture_id" });
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({
    date_from: dateFrom,
    date_to: dateTo,
    inserted_or_updated: rows.length,
    already_present: false,
  });
}
