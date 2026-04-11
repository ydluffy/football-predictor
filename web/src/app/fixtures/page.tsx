"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Fixture } from "@/lib/api";
import { getFixtures, ingestFootballData } from "@/lib/api";

function todayStr(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function FixturesPage() {
  const [date, setDate] = useState(todayStr());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Fixture[]>([]);

  const load = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const r = await getFixtures(date);
      setRows(r.fixtures);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [date]);

  async function ingest() {
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

  const hasScores = useMemo(() => rows.some((r) => r.home_score != null && r.away_score != null), [rows]);

  return (
    <div className="grid gap-4">
      <section className="rounded-xl border border-zinc-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
          <div>
            <div className="text-sm font-semibold">赛程</div>
            <div className="text-xs text-zinc-500">后端：FastAPI `/api/fixtures`</div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"
            />
            <button
              onClick={ingest}
              disabled={busy}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              导入
            </button>
          </div>
        </div>
        {error ? <div className="px-4 py-3 text-sm text-red-600">{error}</div> : null}
        <div className="overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500">
              <tr>
                <th className="px-4 py-2">时间(UTC)</th>
                <th className="px-4 py-2">联赛</th>
                <th className="px-4 py-2">主队</th>
                <th className="px-4 py-2">客队</th>
                <th className="px-4 py-2">状态</th>
                <th className="px-4 py-2">比分</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.fixture_id} className="border-t border-zinc-100">
                  <td className="px-4 py-2 text-zinc-600 tabular-nums">{r.utc_date?.slice(11, 16) || "-"}</td>
                  <td className="px-4 py-2">{r.competition_name || r.competition_code || "-"}</td>
                  <td className="px-4 py-2 font-medium">{r.home_team_name || "-"}</td>
                  <td className="px-4 py-2 font-medium">{r.away_team_name || "-"}</td>
                  <td className="px-4 py-2 text-zinc-600">{r.status || "-"}</td>
                  <td className="px-4 py-2 tabular-nums">
                    {r.home_score != null && r.away_score != null ? `${r.home_score}-${r.away_score}` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-3 text-xs text-zinc-500">
          {rows.length === 0 ? "暂无数据。点击右上角“导入”拉取 football-data.org 数据。" : null}
          {rows.length > 0 && !hasScores ? "提示：部分比赛未结束，比分字段可能为空。" : null}
        </div>
      </section>
    </div>
  );
}

