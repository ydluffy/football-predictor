import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { competitionNameZh, formatLocalTimeFromUtc, statusZh, teamNameZhMaybe } from "@/lib/zh";
import { translateTeamNamesWithCache } from "@/lib/translateTeamNames";
import type { FixtureListRow } from "@/lib/databaseTypes";
import { loadSportteryFixtureBySyntheticId } from "@/lib/sportteryFixtures";

export async function GET(_: Request, context: { params: Promise<{ fixtureId: string }> }) {
  const params = await context.params;
  const fixtureId = Number(params.fixtureId);
  if (!Number.isFinite(fixtureId)) {
    return NextResponse.json({ error: "invalid fixture_id" }, { status: 400 });
  }

  const sportteryFixture = await loadSportteryFixtureBySyntheticId(fixtureId);
  if (sportteryFixture) {
    const fixture = {
      ...sportteryFixture,
      competition_name_zh: competitionNameZh(sportteryFixture.competition_code, sportteryFixture.competition_name),
      status_zh: "在售",
      home_team_name_zh: teamNameZhMaybe(sportteryFixture.home_team_name) || sportteryFixture.home_team_name,
      away_team_name_zh: teamNameZhMaybe(sportteryFixture.away_team_name) || sportteryFixture.away_team_name,
      kickoff_time_zh: formatLocalTimeFromUtc(sportteryFixture.utc_date, "Asia/Shanghai"),
      data_source: "sporttery_sales_day",
    };
    return NextResponse.json({ fixture });
  }

  const { sb, response } = requireSupabaseAdmin();
  if (!sb) return response;
  const { data, error } = await sb
    .from("fixtures")
    .select(
      "fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name,home_score,away_score",
    )
    .eq("fixture_id", fixtureId)
    .maybeSingle();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ fixture: null }, { status: 404 });

  const row = data as FixtureListRow;
  const translated = await translateTeamNamesWithCache([row.home_team_name, row.away_team_name]);

  const fixture = {
    ...row,
    competition_name_zh: competitionNameZh(row.competition_code, row.competition_name),
    status_zh: statusZh(row.status),
    home_team_name_zh: teamNameZhMaybe(row.home_team_name) || translated[(row.home_team_name || "").trim()] || row.home_team_name,
    away_team_name_zh: teamNameZhMaybe(row.away_team_name) || translated[(row.away_team_name || "").trim()] || row.away_team_name,
    kickoff_time_zh: formatLocalTimeFromUtc(row.utc_date, "Asia/Shanghai"),
  };

  return NextResponse.json({ fixture });
}
