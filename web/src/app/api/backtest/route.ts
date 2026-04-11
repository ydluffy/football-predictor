import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

function clamp01(x: number) {
  return Math.max(0, Math.min(1, x));
}

function safeLog(x: number) {
  return Math.log(Math.max(1e-12, x));
}

type Outcome = "H" | "D" | "A";

function outcomeFromScores(home: number, away: number): Outcome {
  if (home > away) return "H";
  if (home < away) return "A";
  return "D";
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const dateFrom = searchParams.get("date_from");
  const dateTo = searchParams.get("date_to");
  if (!dateFrom || !dateTo) return NextResponse.json({ error: "missing date_from/date_to" }, { status: 400 });

  const fromUtc = new Date(`${dateFrom}T00:00:00+08:00`).toISOString();
  const toUtc = new Date(new Date(`${dateTo}T00:00:00+08:00`).getTime() + 24 * 3600 * 1000).toISOString();

  const sb = supabaseAdmin();

  const { data: rows, error } = await sb
    .from("fixture_predictions")
    .select(
      "fixture_id,model_version,generated_at,p_home,p_draw,p_away,confidence,lambda_home,lambda_away,p_over_2_5,p_btts_yes,odds_home,odds_draw,odds_away,ev_home,ev_draw,ev_away,kelly_home,kelly_draw,kelly_away,fixtures:fixtures!inner(fixture_id,utc_date,status,home_team_name,away_team_name,home_score,away_score,competition_code,competition_name)"
    )
    .gte("fixtures.utc_date", fromUtc)
    .lt("fixtures.utc_date", toUtc)
    .eq("fixtures.status", "FINISHED")
    .order("fixtures.utc_date", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const items: any[] = [];
  let n = 0;
  let correct = 0;
  let loglossSum = 0;
  let brierSum = 0;
  const cm = { H: { H: 0, D: 0, A: 0 }, D: { H: 0, D: 0, A: 0 }, A: { H: 0, D: 0, A: 0 } };

  for (const r of rows || []) {
    const fx: any = (r as any).fixtures;
    if (!fx) continue;
    const hs = fx.home_score;
    const as = fx.away_score;
    if (typeof hs !== "number" || typeof as !== "number") continue;
    const kickoff = fx.utc_date ? new Date(fx.utc_date).getTime() : null;
    const gen = r.generated_at ? new Date(r.generated_at).getTime() : null;
    if (kickoff != null && gen != null && gen > kickoff) continue;

    const pH = clamp01(Number(r.p_home));
    const pD = clamp01(Number(r.p_draw));
    const pA = clamp01(Number(r.p_away));
    const s = pH + pD + pA;
    const probs = s > 0 ? { H: pH / s, D: pD / s, A: pA / s } : { H: 1 / 3, D: 1 / 3, A: 1 / 3 };

    const actual = outcomeFromScores(hs, as);
    const pred: Outcome = (Object.entries(probs).sort((a, b) => (b[1] as number) - (a[1] as number))[0][0] as Outcome);

    n += 1;
    if (pred === actual) correct += 1;
    cm[actual][pred] += 1;

    loglossSum += -safeLog(probs[actual]);
    const y = { H: actual === "H" ? 1 : 0, D: actual === "D" ? 1 : 0, A: actual === "A" ? 1 : 0 };
    brierSum += (probs.H - y.H) ** 2 + (probs.D - y.D) ** 2 + (probs.A - y.A) ** 2;

    items.push({
      fixture_id: r.fixture_id,
      utc_date: fx.utc_date,
      competition: fx.competition_name || fx.competition_code,
      home: fx.home_team_name,
      away: fx.away_team_name,
      score: `${hs}-${as}`,
      actual,
      pred,
      p_home: probs.H,
      p_draw: probs.D,
      p_away: probs.A,
      logloss: -safeLog(probs[actual]),
    });
  }

  const summary = {
    model_version: "poisson_v1",
    date_from: dateFrom,
    date_to: dateTo,
    n,
    accuracy: n ? correct / n : null,
    logloss: n ? loglossSum / n : null,
    brier: n ? brierSum / n : null,
    confusion_matrix: cm,
  };

  if (n > 0) {
    await sb.from("backtest_runs").insert({
      model_version: "poisson_v1",
      date_from: dateFrom,
      date_to: dateTo,
      n,
      accuracy: summary.accuracy,
      logloss: summary.logloss,
      brier: summary.brier,
      meta: { confusion_matrix: cm },
    });
  }

  return NextResponse.json({ summary, items });
}

