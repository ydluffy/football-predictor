export type ProbTriple = { p_home: number; p_draw: number; p_away: number };
export type OddsTriple = { odds_home?: number | null; odds_draw?: number | null; odds_away?: number | null };

function clamp(x: number, a: number, b: number) {
  return Math.max(a, Math.min(b, x));
}

export function evAndKelly(prob: ProbTriple, odds: OddsTriple, kellyFraction = 0.25) {
  const oh = clamp((odds.odds_home ?? 0), 1.000001, 1000);
  const od = clamp((odds.odds_draw ?? 0), 1.000001, 1000);
  const oa = clamp((odds.odds_away ?? 0), 1.000001, 1000);
  const ev_home = prob.p_home * oh - 1;
  const ev_draw = prob.p_draw * od - 1;
  const ev_away = prob.p_away * oa - 1;
  const k_home = Math.max(0, (prob.p_home * oh - 1) / (oh - 1)) * kellyFraction;
  const k_draw = Math.max(0, (prob.p_draw * od - 1) / (od - 1)) * kellyFraction;
  const k_away = Math.max(0, (prob.p_away * oa - 1) / (oa - 1)) * kellyFraction;
  let betting_recommendation = "无推荐投注 (EV不足)";
  const best = [
    ["H", ev_home, k_home],
    ["D", ev_draw, k_draw],
    ["A", ev_away, k_away],
  ].sort((a, b) => (b[1] as number) - (a[1] as number))[0] as [string, number, number];
  if (best[1] > 0.05) {
    betting_recommendation = `推荐投注: ${best[0]}, EV: ${best[1].toFixed(3)}, 建议仓位: ${(best[2] * 100).toFixed(1)}%`;
  }
  return {
    ev_home,
    ev_draw,
    ev_away,
    kelly_home: k_home,
    kelly_draw: k_draw,
    kelly_away: k_away,
    betting_recommendation,
  };
}

