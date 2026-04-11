"use client";

import { useEffect, useMemo, useState } from "react";

type StatusResponse = {
  env: {
    hasSupabaseUrl: boolean;
    hasSupabaseServiceRole: boolean;
    hasFootballDataKey: boolean;
    hasOpenRouterKey: boolean;
    hasApiFootballKey?: boolean;
    openRouterModel: string | null;
  };
  supabase: {
    ok: boolean | null;
    fixturesCount: number | null;
    error: string | null;
  };
};

function isoToday() {
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function SetupPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string>("");
  const [dateFrom, setDateFrom] = useState(isoToday());
  const [dateTo, setDateTo] = useState(isoToday());
  const [oddsDate, setOddsDate] = useState(isoToday());
  const [snapshotDate, setSnapshotDate] = useState(isoToday());
  const [btFrom, setBtFrom] = useState(isoToday());
  const [btTo, setBtTo] = useState(isoToday());
  const [btResult, setBtResult] = useState<any | null>(null);

  async function refresh() {
    const r = await fetch("/api/status", { cache: "no-store" });
    const j = (await r.json()) as StatusResponse;
    setStatus(j);
  }

  useEffect(() => {
    refresh();
  }, []);

  const allEnvOk = useMemo(() => {
    if (!status) return false;
    return (
      status.env.hasSupabaseUrl &&
      status.env.hasSupabaseServiceRole &&
      status.env.hasFootballDataKey &&
      status.env.hasOpenRouterKey
    );
  }, [status]);

  async function ingest() {
    setLoading(true);
    setMsg("");
    try {
      const r = await fetch(`/api/ingest/football-data?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`,
        { method: "POST" }
      );
      const t = await r.text();
      if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
      setMsg(`✅ 导入成功：${t}`);
      await refresh();
    } catch (e) {
      setMsg(`❌ 导入失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function ingestOdds() {
    setLoading(true);
    setMsg("");
    try {
      const qs = new URLSearchParams({ date: oddsDate });
      const r = await fetch(`/api/ingest/odds?${qs.toString()}`, { method: "POST" });
      const t = await r.text();
      if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
      setMsg(`✅ 赔率拉取成功：${t}`);
    } catch (e) {
      setMsg(`❌ 赔率拉取失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function snapshotPredictions() {
    setLoading(true);
    setMsg("");
    try {
      const r = await fetch("/api/predictions/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: snapshotDate }),
      });
      const t = await r.text();
      if (!r.ok) throw new Error(t || `HTTP ${r.status}`);
      setMsg(`✅ 预测快照已写入：${t}`);
    } catch (e) {
      setMsg(`❌ 预测快照失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function runBacktest() {
    setLoading(true);
    setMsg("");
    setBtResult(null);
    try {
      const url = `/api/backtest?date_from=${encodeURIComponent(btFrom)}&date_to=${encodeURIComponent(btTo)}`;
      const r = await fetch(url, { cache: "no-store" });
      const j = await r.json();
      if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
      setBtResult(j);
      setMsg("✅ 回测完成（结果已显示在下方）");
    } catch (e) {
      setMsg(`❌ 回测失败：${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 920, margin: "0 auto", padding: 24 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>⚙️ 部署自检 / 一键初始化</h1>
      <p style={{ color: "#666", marginBottom: 16 }}>
        这个页面用于帮你检查 Vercel 环境变量是否配置正确，并提供“一键导入数据”。
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12 }}>
        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, background: "#fff" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ fontSize: 16, fontWeight: 700 }}>环境变量</h2>
            <button onClick={refresh} disabled={loading} style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #ddd" }}>
              刷新
            </button>
          </div>
          {!status ? (
            <p>加载中…</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
              <li>SUPABASE_URL：{status.env.hasSupabaseUrl ? "✅" : "❌"}</li>
              <li>SUPABASE_SERVICE_ROLE_KEY：{status.env.hasSupabaseServiceRole ? "✅" : "❌"}</li>
              <li>FOOTBALL_DATA_API_KEY：{status.env.hasFootballDataKey ? "✅" : "❌"}</li>
              <li>OPENROUTER_API_KEY：{status.env.hasOpenRouterKey ? "✅" : "❌"}</li>
              <li>API_FOOTBALL_KEY（自动赔率）：{status.env.hasApiFootballKey ? "✅" : "❌"}</li>
              <li>OPENROUTER_MODEL：{status.env.openRouterModel || "(未设置，默认 deepseek/deepseek-chat)"}</li>
            </ul>
          )}
          {status?.supabase.ok === false ? (
            <p style={{ marginTop: 10, color: "#b42318" }}>Supabase 连接失败：{status.supabase.error}</p>
          ) : null}
          {status?.supabase.ok === true ? (
            <p style={{ marginTop: 10, color: "#067647" }}>Supabase 连接正常，fixtures 表记录数：{status.supabase.fixturesCount ?? "-"}</p>
          ) : null}
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, background: "#fff" }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>一键导入比赛数据</h2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#555" }}>date_from</span>
              <input value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={{ padding: "8px 10px", border: "1px solid #ddd", borderRadius: 8 }} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#555" }}>date_to</span>
              <input value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={{ padding: "8px 10px", border: "1px solid #ddd", borderRadius: 8 }} />
            </label>
            <button
              onClick={ingest}
              disabled={loading || !allEnvOk}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "0",
                background: allEnvOk ? "#0b5fff" : "#94a3b8",
                color: "#fff",
                fontWeight: 700,
                cursor: loading || !allEnvOk ? "not-allowed" : "pointer",
                marginTop: 18,
              }}
            >
              {loading ? "导入中…" : "导入"}
            </button>
          </div>
          {!allEnvOk ? (
            <p style={{ marginTop: 10, color: "#b42318" }}>请先在 Vercel 设置里补齐缺失的环境变量（上面有 ❌ 的项）。</p>
          ) : null}
          {msg ? <pre style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>{msg}</pre> : null}
          <p style={{ marginTop: 12, color: "#666" }}>
            导入成功后，去 <a href="/fixtures">/fixtures</a> 查看赛程，去 <a href="/predictions">/predictions</a> 查看预测。
          </p>
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, background: "#fff" }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>一键拉取赔率</h2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#555" }}>date</span>
              <input value={oddsDate} onChange={(e) => setOddsDate(e.target.value)} style={{ padding: "8px 10px", border: "1px solid #ddd", borderRadius: 8 }} />
            </label>
            <button
              onClick={ingestOdds}
              disabled={loading || !status?.env?.hasApiFootballKey}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "0",
                background: status?.env?.hasApiFootballKey ? "#0b5fff" : "#94a3b8",
                color: "#fff",
                fontWeight: 700,
                cursor: loading || !status?.env?.hasApiFootballKey ? "not-allowed" : "pointer",
                marginTop: 18,
              }}
            >
              {loading ? "拉取中…" : "拉取赔率"}
            </button>
          </div>
          {!status?.env?.hasApiFootballKey ? (
            <p style={{ marginTop: 10, color: "#b42318" }}>请先在 Vercel 环境变量中配置 API_FOOTBALL_KEY。</p>
          ) : null}
          <p style={{ marginTop: 12, color: "#666" }}>
            赔率写入后，重新打开 <a href="/predictions">/predictions</a> 查看“价值投注建议（EV/Kelly）”。
          </p>
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, background: "#fff" }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>赛前：保存预测快照（用于回测）</h2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#555" }}>date</span>
              <input value={snapshotDate} onChange={(e) => setSnapshotDate(e.target.value)} style={{ padding: "8px 10px", border: "1px solid #ddd", borderRadius: 8 }} />
            </label>
            <button
              onClick={snapshotPredictions}
              disabled={loading}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "0",
                background: "#0b5fff",
                color: "#fff",
                fontWeight: 700,
                cursor: loading ? "not-allowed" : "pointer",
                marginTop: 18,
              }}
            >
              {loading ? "保存中…" : "保存预测快照"}
            </button>
          </div>
          <p style={{ marginTop: 12, color: "#666" }}>
            说明：回测使用“赛前保存的预测快照”对比赛后真实结果，避免信息穿越。
          </p>
        </div>

        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 16, background: "#fff" }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 10 }}>赛后：回测（评估模型预测能力）</h2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#555" }}>date_from</span>
              <input value={btFrom} onChange={(e) => setBtFrom(e.target.value)} style={{ padding: "8px 10px", border: "1px solid #ddd", borderRadius: 8 }} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#555" }}>date_to</span>
              <input value={btTo} onChange={(e) => setBtTo(e.target.value)} style={{ padding: "8px 10px", border: "1px solid #ddd", borderRadius: 8 }} />
            </label>
            <button
              onClick={runBacktest}
              disabled={loading}
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                border: "0",
                background: "#0b5fff",
                color: "#fff",
                fontWeight: 700,
                cursor: loading ? "not-allowed" : "pointer",
                marginTop: 18,
              }}
            >
              {loading ? "回测中…" : "运行回测"}
            </button>
          </div>
          {btResult?.summary ? (
            <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 10, padding: 12, background: "#fafafa" }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>回测摘要</div>
              <div style={{ fontSize: 12, color: "#444", lineHeight: 1.8 }}>
                <div>样本数 n：{btResult.summary.n}</div>
                <div>Accuracy：{btResult.summary.accuracy != null ? (btResult.summary.accuracy * 100).toFixed(1) + "%" : "-"}</div>
                <div>Logloss：{btResult.summary.logloss != null ? btResult.summary.logloss.toFixed(4) : "-"}</div>
                <div>Brier：{btResult.summary.brier != null ? btResult.summary.brier.toFixed(4) : "-"}</div>
              </div>
            </div>
          ) : null}
          <p style={{ marginTop: 12, color: "#666" }}>
            提示：如果 n=0，通常是因为你还没有在赛前保存预测快照，或比赛尚未变为 FINISHED。
          </p>
        </div>
      </div>
    </div>
  );
}
