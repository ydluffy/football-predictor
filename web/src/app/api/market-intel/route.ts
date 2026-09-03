import { NextResponse } from "next/server";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { teamNameZh } from "@/lib/zh";
import { localArtifactsEnabled } from "@/lib/localArtifacts";

type InputFixture = {
  fixture_id: number;
  utc_date?: string | null;
  home_team_name?: string | null;
  home_team_name_zh?: string | null;
  away_team_name?: string | null;
  away_team_name_zh?: string | null;
};

type MovementRow = {
  home_team: string;
  away_team: string;
  kickoff_at: string;
  snapshot_count: number;
  bookmaker_count: number;
  opening_captured_at: string | null;
  latest_captured_at: string | null;
  opening_home_handicap_median: number | null;
  latest_home_handicap_median: number | null;
  home_line_strength_delta: number | null;
  home_price_probability_delta: number | null;
  line_strength_per_hour: number | null;
  favorite_hot_without_line_support: boolean;
  line_upgrade_without_price_support: boolean;
  line_downgrade: boolean;
  safe_for_shadow_features: boolean;
};

type AlignmentRow = {
  match_id: string;
  home_team: string;
  away_team: string;
  kickoff_at: string;
  sporttery_captured_at: string | null;
  outer_captured_at: string | null;
  sporttery_handicap: number | null;
  outer_home_handicap: number | null;
  sporttery_minus_outer_handicap: number | null;
  time_delta_minutes: number | null;
  time_aligned: boolean;
  bookmaker_name: string;
};

function normalizeName(s?: string | null) {
  return (s || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function shanghaiDate(iso?: string | null) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function numeric(value: string | undefined) {
  if (!value || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function boolish(value: string | undefined) {
  return String(value || "").toLowerCase() === "true";
}

function parseCsv(content: string) {
  const lines = content.replace(/^\uFEFF/, "").trim().split(/\r?\n/);
  if (lines.length <= 1) return [];
  const header = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const cells = line.split(",");
    return Object.fromEntries(header.map((key, index) => [key, cells[index] ?? ""]));
  });
}

async function resolveExistingFile(candidates: string[]) {
  for (const filePath of candidates) {
    try {
      await access(filePath);
      return filePath;
    } catch {}
  }
  return null;
}

async function loadMovementRows() {
  if (!localArtifactsEnabled()) return [] as MovementRow[];
  const cwd = process.cwd();
  const filePath = await resolveExistingFile([
    path.resolve(cwd, "..", "football-predictor", "data", "processed", "handicap_market_movement_latest.csv"),
    path.resolve(cwd, "football-predictor", "data", "processed", "handicap_market_movement_latest.csv"),
  ]);
  if (!filePath) return [] as MovementRow[];

  const content = await readFile(/* turbopackIgnore: true */ filePath, "utf8");
  return parseCsv(content).map((row) => ({
    home_team: String(row.home_team || ""),
    away_team: String(row.away_team || ""),
    kickoff_at: String(row.kickoff_at || ""),
    snapshot_count: Number(row.snapshot_count || 0),
    bookmaker_count: Number(row.bookmaker_count || 0),
    opening_captured_at: String(row.opening_captured_at || "") || null,
    latest_captured_at: String(row.latest_captured_at || "") || null,
    opening_home_handicap_median: numeric(row.opening_home_handicap_median),
    latest_home_handicap_median: numeric(row.latest_home_handicap_median),
    home_line_strength_delta: numeric(row.home_line_strength_delta),
    home_price_probability_delta: numeric(row.home_price_probability_delta),
    line_strength_per_hour: numeric(row.line_strength_per_hour),
    favorite_hot_without_line_support: boolish(row.favorite_hot_without_line_support),
    line_upgrade_without_price_support: boolish(row.line_upgrade_without_price_support),
    line_downgrade: boolish(row.line_downgrade),
    safe_for_shadow_features: boolish(row.safe_for_shadow_features),
  }));
}

async function loadAlignmentRows() {
  if (!localArtifactsEnabled()) return [] as AlignmentRow[];
  const cwd = process.cwd();
  const filePath = await resolveExistingFile([
    path.resolve(cwd, "..", "football-predictor", "artifacts", "data", "inner_outer_market_alignment_latest.csv"),
    path.resolve(cwd, "football-predictor", "artifacts", "data", "inner_outer_market_alignment_latest.csv"),
  ]);
  if (!filePath) return [] as AlignmentRow[];

  const content = await readFile(/* turbopackIgnore: true */ filePath, "utf8");
  return parseCsv(content).map((row) => ({
    match_id: String(row.match_id || ""),
    home_team: String(row.home_team || ""),
    away_team: String(row.away_team || ""),
    kickoff_at: String(row.kickoff_at || ""),
    sporttery_captured_at: String(row.sporttery_captured_at || "") || null,
    outer_captured_at: String(row.outer_captured_at || "") || null,
    sporttery_handicap: numeric(row.sporttery_handicap),
    outer_home_handicap: numeric(row.outer_home_handicap),
    sporttery_minus_outer_handicap: numeric(row.sporttery_minus_outer_handicap),
    time_delta_minutes: numeric(row.time_delta_minutes),
    time_aligned: boolish(row.time_aligned),
    bookmaker_name: String(row.bookmaker_name || ""),
  }));
}

function candidateNames(fixture: InputFixture) {
  return {
    home: new Set(
      [
        fixture.home_team_name,
        fixture.home_team_name_zh,
        teamNameZh(fixture.home_team_name),
        teamNameZh(fixture.home_team_name_zh),
      ]
        .map(normalizeName)
        .filter(Boolean),
    ),
    away: new Set(
      [
        fixture.away_team_name,
        fixture.away_team_name_zh,
        teamNameZh(fixture.away_team_name),
        teamNameZh(fixture.away_team_name_zh),
      ]
        .map(normalizeName)
        .filter(Boolean),
    ),
  };
}

function sameFixture(fixture: InputFixture, homeTeam: string, awayTeam: string, kickoffAt: string) {
  const names = candidateNames(fixture);
  const home = normalizeName(homeTeam);
  const away = normalizeName(awayTeam);
  const kickoffDate = shanghaiDate(kickoffAt);
  const fixtureDate = shanghaiDate(fixture.utc_date);
  return names.home.has(home) && names.away.has(away) && kickoffDate != null && kickoffDate === fixtureDate;
}

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as { fixtures?: InputFixture[] };
    const fixtures = body.fixtures || [];
    if (!fixtures.length) {
      return NextResponse.json({ count: 0, items: [] });
    }

    const [movementRows, alignmentRows] = await Promise.all([loadMovementRows(), loadAlignmentRows()]);

    const groupedAlignment = new Map<
      string,
      {
        sample: AlignmentRow;
        outerValues: number[];
        diffValues: number[];
        deltaValues: number[];
        bookmakers: Set<string>;
        anyAligned: boolean;
        bestRow: AlignmentRow | null;
      }
    >();

    for (const row of alignmentRows) {
      const current = groupedAlignment.get(row.match_id) || {
        sample: row,
        outerValues: [],
        diffValues: [],
        deltaValues: [],
        bookmakers: new Set<string>(),
        anyAligned: false,
        bestRow: null,
      };
      if (typeof row.outer_home_handicap === "number") current.outerValues.push(row.outer_home_handicap);
      if (typeof row.sporttery_minus_outer_handicap === "number") current.diffValues.push(row.sporttery_minus_outer_handicap);
      if (typeof row.time_delta_minutes === "number") current.deltaValues.push(row.time_delta_minutes);
      if (row.bookmaker_name) current.bookmakers.add(row.bookmaker_name);
      current.anyAligned = current.anyAligned || row.time_aligned;
      if (
        current.bestRow == null ||
        ((row.time_delta_minutes ?? Number.POSITIVE_INFINITY) <
          (current.bestRow.time_delta_minutes ?? Number.POSITIVE_INFINITY))
      ) {
        current.bestRow = row;
      }
      groupedAlignment.set(row.match_id, current);
    }

    const items = fixtures.map((fixture) => {
      const movement =
        movementRows.find((row) => sameFixture(fixture, row.home_team, row.away_team, row.kickoff_at)) || null;

      const alignmentEntry =
        [...groupedAlignment.values()].find((entry) =>
          sameFixture(fixture, entry.sample.home_team, entry.sample.away_team, entry.sample.kickoff_at),
        ) || null;

      const movementPayload = movement
        ? {
            opening_captured_at: movement.opening_captured_at,
            latest_captured_at: movement.latest_captured_at,
            opening_home_handicap_median: movement.opening_home_handicap_median,
            latest_home_handicap_median: movement.latest_home_handicap_median,
            home_line_strength_delta: movement.home_line_strength_delta,
            home_price_probability_delta: movement.home_price_probability_delta,
            line_strength_per_hour: movement.line_strength_per_hour,
            snapshot_count: movement.snapshot_count,
            bookmaker_count: movement.bookmaker_count,
            favorite_hot_without_line_support: movement.favorite_hot_without_line_support,
            line_upgrade_without_price_support: movement.line_upgrade_without_price_support,
            line_downgrade: movement.line_downgrade,
            safe_for_shadow_features: movement.safe_for_shadow_features,
          }
        : null;

      const alignmentPayload = alignmentEntry
        ? {
            sporttery_handicap: alignmentEntry.sample.sporttery_handicap,
            outer_home_handicap_median:
              alignmentEntry.outerValues.length > 0
                ? alignmentEntry.outerValues.sort((a, b) => a - b)[Math.floor(alignmentEntry.outerValues.length / 2)]
                : null,
            sporttery_minus_outer_handicap_median:
              alignmentEntry.diffValues.length > 0
                ? alignmentEntry.diffValues.sort((a, b) => a - b)[Math.floor(alignmentEntry.diffValues.length / 2)]
                : null,
            aligned_bookmaker_count: alignmentEntry.bookmakers.size,
            time_aligned: alignmentEntry.anyAligned,
            min_time_delta_minutes:
              alignmentEntry.deltaValues.length > 0 ? Math.min(...alignmentEntry.deltaValues) : null,
            sporttery_captured_at: alignmentEntry.bestRow?.sporttery_captured_at || null,
            outer_captured_at: alignmentEntry.bestRow?.outer_captured_at || null,
          }
        : null;

      return {
        fixture_id: fixture.fixture_id,
        movement: movementPayload,
        alignment: alignmentPayload,
      };
    });

    return NextResponse.json({ count: items.length, items });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
