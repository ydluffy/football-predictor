import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { localArtifactsEnabled } from "@/lib/localArtifacts";
import { buildSportteryFixtureId } from "@/lib/sportteryFixtures";

type SportteryMatchAnalysisRow = {
  match_number: string;
  competition: string;
  kickoff_time: string;
  handicap: string;
  favorite_label: string;
  favorite_probability: string;
  draw_probability: string;
  market_shape: string;
  market_signal_note: string;
  script: string;
  total_goals_suggestion: string;
  correct_score_suggestion: string;
  half_full_suggestion: string;
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

function parseCsvLine(line: string) {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        const next = line[i + 1];
        if (next === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += ch;
      }
    } else {
      if (ch === ",") {
        out.push(cur);
        cur = "";
      } else if (ch === '"') {
        inQuotes = true;
      } else {
        cur += ch;
      }
    }
  }
  out.push(cur);
  return out;
}

function parseCsv(content: string) {
  const lines = content.replace(/^\uFEFF/, "").trim().split(/\r?\n/);
  if (lines.length <= 1) return [];
  const header = parseCsvLine(lines[0]).map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return Object.fromEntries(header.map((key, index) => [key, cells[index] ?? ""])) as Record<string, string>;
  });
}

async function findLatestSportteryMatchAnalysisFile(salesDay: string) {
  const dataDir = await firstExistingDir(dataDirCandidates());
  if (!dataDir) return null;
  const files = await readdir(/* turbopackIgnore: true */ dataDir);
  const matches = files
    .filter((name) => new RegExp(`^sporttery_match_analysis_${salesDay}_(\\d{4}).*\\.csv$`).test(name))
    .sort((a, b) => b.localeCompare(a));
  if (matches.length === 0) return null;
  return path.join(/* turbopackIgnore: true */ dataDir, matches[0]);
}

function num(text: string) {
  const n = Number(String(text || "").trim());
  return Number.isFinite(n) ? n : null;
}

function clamp01(x: number) {
  return Math.max(0, Math.min(1, x));
}

function parseKickoffLocal(text: string | null) {
  // 输入示例：2026-09-02 02:45
  if (!text) return null;
  const m = text.trim().match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);
  if (!m) return null;
  return `${m[1]}T${m[2]}:00+08:00`;
}

export type SportteryPredictionSeed = {
  fixture_id: number;
  match_number: string;
  competition: string;
  kickoff_at: string | null;
  handicap: number | null;
  p_home: number;
  p_draw: number;
  p_away: number;
  factors: string[];
  raw: SportteryMatchAnalysisRow;
};

export async function loadSportteryPredictionSeedsBySalesDay(salesDay: string): Promise<SportteryPredictionSeed[]> {
  const filePath = await findLatestSportteryMatchAnalysisFile(salesDay);
  if (!filePath) return [];
  const rawText = await readFile(/* turbopackIgnore: true */ filePath, "utf8");
  const rows = parseCsv(rawText) as unknown as SportteryMatchAnalysisRow[];

  const out: SportteryPredictionSeed[] = [];
  for (const r of rows) {
    const rawMatchNumber = String((r as any).match_number || "").trim();
    if (!rawMatchNumber) continue;
    const matchNumber = rawMatchNumber.padStart(3, "0");

    const favoriteProb = num((r as any).favorite_probability) ?? null;
    const drawProb = num((r as any).draw_probability) ?? null;
    const favLabel = String((r as any).favorite_label || "").trim();
    if (favoriteProb == null || drawProb == null) continue;

    const remaining = clamp01(1 - favoriteProb - drawProb);
    const pHome = favLabel.includes("主") ? favoriteProb : remaining;
    const pAway = favLabel.includes("客") ? favoriteProb : remaining;

    const handicap = num((r as any).handicap);
    const kickoffAt = parseKickoffLocal(String((r as any).kickoff_time || ""));

    const factors: string[] = [];
    factors.push("来源：体彩赛程匹配的盘口锚定分析（sporttery_match_analysis）");
    if (typeof handicap === "number") factors.push(`体彩让球：${handicap > 0 ? "+" : ""}${handicap}`);
    if ((r as any).market_shape) factors.push(`市场形态：${String((r as any).market_shape)}`);
    if ((r as any).script) factors.push(`脚本：${String((r as any).script)}`);
    if ((r as any).market_signal_note) factors.push(`市场备注：${String((r as any).market_signal_note)}`);

    out.push({
      fixture_id: buildSportteryFixtureId(salesDay, matchNumber),
      match_number: matchNumber,
      competition: String((r as any).competition || ""),
      kickoff_at: kickoffAt,
      handicap: typeof handicap === "number" ? handicap : null,
      p_home: clamp01(pHome),
      p_draw: clamp01(drawProb),
      p_away: clamp01(pAway),
      factors,
      raw: r,
    });
  }

  return out;
}
