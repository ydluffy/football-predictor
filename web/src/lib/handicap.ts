import type { Prediction } from "@/lib/api";
import { scorelineMatrix } from "@/lib/poisson";

export type SportteryHandicapEvaluation = {
  handicap: number;
  lineText: string;
  compactText: string;
  logicHint: string;
  p_let_win: number;
  p_let_draw: number;
  p_let_lose: number;
  topLabel: "让胜" | "让平" | "让负";
  topProbability: number;
  summary: string;
};

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function formatSportteryHandicapLine(handicap: number) {
  if (handicap > 0) return `主队受让 +${handicap}`;
  if (handicap < 0) return `主队让球 ${handicap}`;
  return "平手盘";
}

export function formatSportteryHandicapCompact(handicap: number) {
  const sign = handicap > 0 ? `+${handicap}` : `${handicap}`;
  return `主队(${sign})`;
}

function logicHint(handicap: number, label: "让胜" | "让平" | "让负") {
  const abs = Math.abs(handicap);
  if (handicap === 0) {
    if (label === "让胜") return "等价于主胜";
    if (label === "让平") return "等价于平局";
    return "等价于客胜";
  }
  if (handicap < 0) {
    // 主队让球（例如 -1）
    if (label === "让胜") return `净胜≥${abs + 1}`;
    if (label === "让平") return `净胜=${abs}`;
    return "不胜/净胜≤0";
  }
  // 主队受让（例如 +1）
  if (label === "让胜") return "不败(胜/平)";
  if (label === "让平") return `输${abs}球`;
  return `输≥${abs + 1}球`;
}

export function evaluateSportteryHandicap(
  prediction?: Prediction | null,
  handicap?: number | null,
): SportteryHandicapEvaluation | null {
  if (!prediction || handicap == null || !Number.isFinite(handicap)) return null;
  if (!Number.isFinite(prediction.lambda_home) || !Number.isFinite(prediction.lambda_away)) return null;

  const lineText = formatSportteryHandicapLine(handicap);
  const compactText = formatSportteryHandicapCompact(handicap);
  const { matrix } = scorelineMatrix(prediction.lambda_home, prediction.lambda_away, 8);

  let letWin = 0;
  let letDraw = 0;
  let letLose = 0;
  let total = 0;

  for (let homeGoals = 0; homeGoals < matrix.length; homeGoals++) {
    for (let awayGoals = 0; awayGoals < matrix[homeGoals].length; awayGoals++) {
      const p = matrix[homeGoals][awayGoals];
      total += p;
      const adjustedHome = homeGoals + handicap;
      if (adjustedHome > awayGoals) letWin += p;
      else if (adjustedHome === awayGoals) letDraw += p;
      else letLose += p;
    }
  }

  if (total <= 0) return null;

  const pLetWin = letWin / total;
  const pLetDraw = letDraw / total;
  const pLetLose = letLose / total;

  const sorted = [
    { label: "让胜" as const, value: pLetWin },
    { label: "让平" as const, value: pLetDraw },
    { label: "让负" as const, value: pLetLose },
  ].sort((a, b) => b.value - a.value);

  const top = sorted[0];
  const second = sorted[1];
  const gap = top.value - second.value;

  let summary = `${lineText}，倾向${top.label} ${pct(top.value)}`;
  if (gap < 0.06) {
    summary += "，分歧较大";
  } else if (top.label === "让平") {
    summary += "，一球差附近概率偏高";
  } else if (top.value >= 0.5) {
    summary += "，方向相对集中";
  }

  return {
    handicap,
    lineText,
    compactText,
    logicHint: logicHint(handicap, top.label),
    p_let_win: pLetWin,
    p_let_draw: pLetDraw,
    p_let_lose: pLetLose,
    topLabel: top.label,
    topProbability: top.value,
    summary,
  };
}
