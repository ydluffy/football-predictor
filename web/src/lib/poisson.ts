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

