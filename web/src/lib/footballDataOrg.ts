export type FootballDataOrgMatch = {
  id: number;
  matchday?: number | null;
  utcDate?: string | null;
  status?: string | null;
  competition?: { name?: string | null } | null;
  season?: { startDate?: string | null } | null;
  score?: { fullTime?: { home?: number | null; away?: number | null } | null } | null;
  homeTeam?: { id?: number | null; shortName?: string | null; name?: string | null } | null;
  awayTeam?: { id?: number | null; shortName?: string | null; name?: string | null } | null;
};

export type FixtureRow = {
  fixture_id: number;
  competition_code: string;
  competition_name: string | null;
  season: number | null;
  matchday: number | null;
  utc_date: string | null;
  status: string | null;
  home_team_id: number | null;
  home_team_name: string | null;
  away_team_id: number | null;
  away_team_name: string | null;
  home_score: number | null;
  away_score: number | null;
};

const DEFAULT_MAJOR_LEAGUES = ["PL", "PD", "SA", "BL1", "FL1"];

function footballDataApiKey() {
  return process.env.FOOTBALL_DATA_API_KEY || process.env.FOOTBALLDATA_API_KEY;
}

export async function fetchMajorLeagueMatches(dateFrom: string, dateTo: string, competitions?: string[]) {
  const key = footballDataApiKey();
  if (!key) throw new Error("missing FOOTBALL_DATA_API_KEY");

  const out: FixtureRow[] = [];
  for (const code of competitions || DEFAULT_MAJOR_LEAGUES) {
    const url = new URL(`https://api.football-data.org/v4/competitions/${code}/matches`);
    url.searchParams.set("dateFrom", dateFrom);
    url.searchParams.set("dateTo", dateTo);

    const resp = await fetch(url.toString(), {
      headers: {
        "X-Auth-Token": key,
        Accept: "application/json",
      },
      cache: "no-store",
    });
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`football-data.org http ${resp.status}: ${txt.slice(0, 500)}`);
    }
    const payload = (await resp.json()) as { matches?: FootballDataOrgMatch[] };
    const matches = payload.matches || [];

    for (const m of matches) {
      const ft = m.score?.fullTime || {};
      const seasonYear = (m.season?.startDate || "").slice(0, 4);
      out.push({
        fixture_id: Number(m.id),
        competition_code: code,
        competition_name: m.competition?.name || null,
        season: seasonYear ? Number(seasonYear) : null,
        matchday: m.matchday ?? null,
        utc_date: m.utcDate || null,
        status: m.status || null,
        home_team_id: (m.homeTeam?.id as number | null) ?? null,
        home_team_name: m.homeTeam?.shortName || m.homeTeam?.name || null,
        away_team_id: (m.awayTeam?.id as number | null) ?? null,
        away_team_name: m.awayTeam?.shortName || m.awayTeam?.name || null,
        home_score: (ft.home as number | null) ?? null,
        away_score: (ft.away as number | null) ?? null,
      });
    }

    await new Promise((r) => setTimeout(r, 6500));
  }

  return out;
}

