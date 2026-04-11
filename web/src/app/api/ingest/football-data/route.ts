import { NextResponse } from "next/server";
import { fetchMajorLeagueMatches } from "@/lib/footballDataOrg";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export async function POST(req: Request) {
  const { searchParams } = new URL(req.url);
  const dateFrom = searchParams.get("date_from");
  const dateTo = searchParams.get("date_to");

  if (!dateFrom || !dateTo) {
    return NextResponse.json({ error: "missing date_from/date_to" }, { status: 400 });
  }

  const rows = await fetchMajorLeagueMatches(dateFrom, dateTo);
  const sb = supabaseAdmin();
  const { error } = await sb.from("fixtures").upsert(rows, { onConflict: "fixture_id" });
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({
    date_from: dateFrom,
    date_to: dateTo,
    inserted_or_updated: rows.length,
  });
}

