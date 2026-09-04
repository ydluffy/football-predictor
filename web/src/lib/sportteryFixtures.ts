import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import type { FixtureListRow } from "@/lib/databaseTypes";
import { localArtifactsEnabled } from "@/lib/localArtifacts";

type SportteryScanFixture = {
  match_id?: string;
  match_number?: string;
  competition?: string;
  competition_id?: string;
  competition_display_name?: string;
  kickoff?: string;
  home_team?: string;
  away_team?: string;
  sale_status?: string;
};

type SportteryScanPayload = {
  sales_day?: string;
  scanned_at?: string;
  fixtures?: SportteryScanFixture[];
};

function dataDirCandidates() {
  if (!localArtifactsEnabled()) return [];
  const cwd = process.cwd();
  return [
    path.resolve(cwd, "..", "football-predictor", "artifacts", "data"),
    path.resolve(cwd, "football-predictor", "artifacts", "data"),
  ];
}

async function firstExistingDir(paths: string[]) {
  for (const candidate of paths) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }
  return null;
}

export function buildSportteryFixtureId(salesDay: string, matchNumber: string) {
  const compactDate = salesDay.replace(/-/g, "");
  const paddedMatch = String(matchNumber || "").padStart(3, "0");
  return Number(`${compactDate}${paddedMatch}`);
}

export function parseSportteryFixtureId(fixtureId: number) {
  const text = String(fixtureId).trim();
  const matched = text.match(/^(\d{4})(\d{2})(\d{2})(\d{3})$/);
  if (!matched) return null;
  return {
    salesDay: `${matched[1]}-${matched[2]}-${matched[3]}`,
    matchNumber: matched[4],
  };
}

function mapSaleStatus(status?: string) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "on_sale") return "SCHEDULED";
  if (normalized === "finished") return "FINISHED";
  return "TIMED";
}

function toFixtureRow(salesDay: string, item: SportteryScanFixture): FixtureListRow {
  const matchNumber = String(item.match_number || "").trim().padStart(3, "0");
  return {
    fixture_id: buildSportteryFixtureId(salesDay, matchNumber),
    competition_code: item.competition_id || item.competition || "SPORTTERY",
    competition_name: item.competition_display_name || item.competition || "体彩赛程",
    utc_date: item.kickoff || null,
    status: mapSaleStatus(item.sale_status),
    home_team_id: null,
    home_team_name: item.home_team || null,
    away_team_id: null,
    away_team_name: item.away_team || null,
    home_score: null,
    away_score: null,
  };
}

async function findLatestSportteryScanFile(salesDay: string) {
  const dataDir = await firstExistingDir(dataDirCandidates());
  if (!dataDir) return null;
  const files = await readdir(/* turbopackIgnore: true */ dataDir);
  const matches = files
    .filter((name) => new RegExp(`^sporttery_sales_window_scan_${salesDay}_(\\d{4})_confirm\\.json$`).test(name))
    .sort((a, b) => b.localeCompare(a));
  if (matches.length === 0) return null;
  return path.join(/* turbopackIgnore: true */ dataDir, matches[0]);
}

export async function loadSportteryFixturesBySalesDay(salesDay: string): Promise<FixtureListRow[]> {
  const filePath = await findLatestSportteryScanFile(salesDay);
  if (!filePath) return [];
  const raw = await readFile(/* turbopackIgnore: true */ filePath, "utf8");
  const payload = JSON.parse(raw) as SportteryScanPayload;
  const effectiveSalesDay = payload.sales_day || salesDay;
  return (payload.fixtures || [])
    .filter((item) => String(item.match_number || "").trim())
    .map((item) => toFixtureRow(effectiveSalesDay, item));
}

export async function loadSportteryFixtureBySyntheticId(fixtureId: number): Promise<FixtureListRow | null> {
  const parsed = parseSportteryFixtureId(fixtureId);
  if (!parsed) return null;
  const rows = await loadSportteryFixturesBySalesDay(parsed.salesDay);
  return rows.find((row) => row.fixture_id === fixtureId) || null;
}
