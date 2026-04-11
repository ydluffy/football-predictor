import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { competitionNameZh, formatLocalTimeFromUtc, statusZh, teamNameZhMaybe } from "@/lib/zh";
import { translateTeamNamesWithCache } from "@/lib/translateTeamNames";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get("date");
  if (!date) return NextResponse.json({ error: "missing date" }, { status: 400 });

  // Interpret the provided YYYY-MM-DD as Asia/Shanghai local day and convert to UTC window.
  const fromLocal = new Date(`${date}T00:00:00+08:00`);
  const toLocal = new Date(fromLocal.getTime() + 24 * 3600 * 1000);
  const from = fromLocal.toISOString();
  const to = toLocal.toISOString();

  const sb = supabaseAdmin();
  const { data, error } = await sb
    .from("fixtures")
    .select(
      "fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name,home_score,away_score"
    )
    .gte("utc_date", from)
    .lt("utc_date", to)
    .order("utc_date", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const names = (data || []).flatMap((f: any) => [f.home_team_name, f.away_team_name]);
  const translated = await translateTeamNamesWithCache(names);

  const fixtures = (data || []).map((f: any) => ({
    ...f,
    competition_name_zh: competitionNameZh(f.competition_code, f.competition_name),
    status_zh: statusZh(f.status),
    home_team_name_zh: teamNameZhMaybe(f.home_team_name) || translated[(f.home_team_name || "").trim()] || f.home_team_name,
    away_team_name_zh: teamNameZhMaybe(f.away_team_name) || translated[(f.away_team_name || "").trim()] || f.away_team_name,
    kickoff_time_zh: formatLocalTimeFromUtc(f.utc_date, "Asia/Shanghai"),
  }));

  return NextResponse.json({
    date_from: date,
    date_to: date,
    count: fixtures.length,
    fixtures,
  });
}
