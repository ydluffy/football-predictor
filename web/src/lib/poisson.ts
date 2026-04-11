function factorial(n: number) {
  let out = 1;
  for (let i = 2; i <= n; i++) out *= i;
  return out;
}

export function poissonPmf(k: number, lambda: number) {
  if (lambda <= 0) return k === 0 ? 1 : 0;
  return (Math.exp(-lambda) * Math.pow(lambda, k)) / factorial(k);
}

export function winDrawLoseFromLambdas(lambdaHome: number, lambdaAway: number, maxGoals = 8) {
  let pHome = 0;
  let pDraw = 0;
  let pAway = 0;

  const ph: number[] = [];
  const pa: number[] = [];
  for (let i = 0; i <= maxGoals; i++) {
    ph.push(poissonPmf(i, lambdaHome));
    pa.push(poissonPmf(i, lambdaAway));
  }

  for (let i = 0; i <= maxGoals; i++) {
    for (let j = 0; j <= maxGoals; j++) {
      const p = ph[i] * pa[j];
      if (i > j) pHome += p;
      else if (i === j) pDraw += p;
      else pAway += p;
    }
  }

  const total = pHome + pDraw + pAway;
  if (total <= 0) return { p_home: 1 / 3, p_draw: 1 / 3, p_away: 1 / 3 };
  return { p_home: pHome / total, p_draw: pDraw / total, p_away: pAway / total };
}

export function scorelineMatrix(lambdaHome: number, lambdaAway: number, maxGoals = 6) {
  const ph: number[] = [];
  const pa: number[] = [];
  for (let i = 0; i <= maxGoals; i++) {
    ph.push(poissonPmf(i, lambdaHome));
    pa.push(poissonPmf(i, lambdaAway));
  }
  const matrix: number[][] = [];
  for (let i = 0; i <= maxGoals; i++) {
    const row: number[] = [];
    for (let j = 0; j <= maxGoals; j++) {
      row.push(ph[i] * pa[j]);
    }
    matrix.push(row);
  }
  return { matrix, maxGoals };
}

export function topScorelines(lambdaHome: number, lambdaAway: number, maxGoals = 6, topN = 5) {
  const { matrix } = scorelineMatrix(lambdaHome, lambdaAway, maxGoals);
  const items: Array<{ home_goals: number; away_goals: number; p: number }> = [];
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      items.push({ home_goals: i, away_goals: j, p: matrix[i][j] });
    }
  }
  items.sort((a, b) => b.p - a.p);
  return items.slice(0, topN);
}

export function totalsProbs(lambdaHome: number, lambdaAway: number, maxGoals = 8) {
  const { matrix } = scorelineMatrix(lambdaHome, lambdaAway, maxGoals);
  let pOver25 = 0;
  let pBttsYes = 0;
  let pTotal = 0;
  for (let i = 0; i < matrix.length; i++) {
    for (let j = 0; j < matrix[i].length; j++) {
      const p = matrix[i][j];
      pTotal += p;
      if (i + j >= 3) pOver25 += p;
      if (i >= 1 && j >= 1) pBttsYes += p;
    }
  }
  if (pTotal <= 0) {
    return { p_over_2_5: 0.5, p_under_2_5: 0.5, p_btts_yes: 0.5, p_btts_no: 0.5 };
  }
  const over = pOver25 / pTotal;
  const btts = pBttsYes / pTotal;
  return { p_over_2_5: over, p_under_2_5: 1 - over, p_btts_yes: btts, p_btts_no: 1 - btts };
}
