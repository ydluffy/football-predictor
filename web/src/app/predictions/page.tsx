"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Fixture, Prediction } from "@/lib/api";
import { getFixtures, getPredictionsByDate, ingestFootballData } from "@/lib/api";
import { ProbBar } from "@/components/ProbBar";
import { competitionNameZh, formatLocalTimeFromUtc, teamNameZh } from "@/lib/zh";

function todayStr(): string {
  // Asia/Shanghai today
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function PredictionsPage() {
  const [date, setDate] = useState(todayStr());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [preds, setPreds] = useState<Prediction[]>([]);

  const load = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const f = await getFixtures(date);
      setFixtures(f.fixtures);
      const p = await getPredictionsByDate(date);
      setPreds(p.predictions);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPreds([]);
    } finally {
      setBusy(false);
    }
  }, [date]);

  async function ingestAndLoad() {
    setError(null);
    setBusy(true);
    try {
      await ingestFootballData(date, date);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load();
  }, [load]);

  const byId = useMemo(() => {
    const m = new Map<number, Fixture>();
    for (const f of fixtures) m.set(f.fixture_id, f);
    return m;
  }, [fixtures]);

  return (
    <div className="grid gap-4">
      <section className="rounded-xl border border-zinc-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
          <div>
            <div className="text-sm font-semibold">预测</div>
            <div className="text-xs text-zinc-500">后端：FastAPI `/api/predictions`（泊松基线）</div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"
            />
            <button
              onClick={ingestAndLoad}
              disabled={busy}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
            >
              导入并刷新
            </button>
          </div>
        </div>
        {error ? <div className="px-4 py-3 text-sm text-red-600">{error}</div> : null}
        <div className="grid gap-3 p-4 md:grid-cols-2">
          {preds.map((p) => {
            const fx = byId.get(p.fixture_id);
            return (
              <div key={p.fixture_id} className="rounded-xl border border-zinc-200 bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold">
                      {(fx?.home_team_name_zh || teamNameZh(fx?.home_team_name)) || "主队"} vs {(fx?.away_team_name_zh || teamNameZh(fx?.away_team_name)) || "客队"}
                    </div>
                    <div className="mt-0.5 text-xs text-zinc-500">
                      {fx?.competition_name_zh || competitionNameZh(fx?.competition_code, fx?.competition_name)} · {fx?.kickoff_time_zh || formatLocalTimeFromUtc(fx?.utc_date, "Asia/Shanghai")}
                      <span className="ml-2 text-zinc-400">(UTC {fx?.utc_date?.slice(11, 16) || "-"})</span>
                    </div>
                  </div>
                  <div className="rounded-full bg-zinc-100 px-3 py-1 text-xs tabular-nums text-zinc-700">
                    置信 {Math.round(p.confidence * 100)}%
                  </div>
                </div>
                <div className="mt-3 grid gap-2">
                  <ProbBar label="主胜" value={p.p_home} />
                  <ProbBar label="平" value={p.p_draw} />
                  <ProbBar label="客胜" value={p.p_away} />
                </div>
                <div className="mt-3 text-xs text-zinc-600">
                  <div className="text-zinc-500">关键因素</div>
                  <ul className="mt-1 list-disc pl-5">
                    {p.factors.slice(0, 3).map((t, idx) => (
                      <li key={idx} className="leading-5">
                        {t}
                      </li>
                    ))}
                  </ul>
                </div>
                {"betting_recommendation" in p ? (
                  <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                    <div className="font-semibold">价值投注建议</div>
                    <div className="mt-1">
                      {p.betting_recommendation || "未提供赔率，无法计算 EV/Kelly"}
                    </div>
                  </div>
                ) : null}

                {p.scorelines_top?.length ? (
                  <div className="mt-3 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-700">
                    <div className="font-semibold">比分 / 大小球（基于泊松 λ）</div>
                    <div className="mt-1 text-zinc-600">
                      Top比分：
                      {p.scorelines_top
                        .slice(0, 3)
                        .map((s) => `${s.home_goals}-${s.away_goals}(${Math.round(s.p * 100)}%)`)
                        .join("，")}
                    </div>
                    <div className="mt-1 text-zinc-600">
                      大2.5：{p.p_over_2_5 != null ? `${Math.round(p.p_over_2_5 * 100)}%` : "-"}，小2.5：
                      {p.p_under_2_5 != null ? `${Math.round(p.p_under_2_5 * 100)}%` : "-"}
                      ，双方进球：{p.p_btts_yes != null ? `${Math.round(p.p_btts_yes * 100)}%` : "-"}
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        <div className="px-4 pb-4 text-xs text-zinc-500">
          {preds.length === 0 ? "暂无预测。先导入赛程后再生成预测。" : null}
        </div>
      </section>
    </div>
  );
}

