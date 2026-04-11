"use client";

import { useEffect, useMemo, useState } from "react";

type StatusResponse = {
  env: {
    hasSupabaseUrl: boolean;
    hasSupabaseServiceRole: boolean;
    hasFootballDataKey: boolean;
    hasOpenRouterKey: boolean;
    openRouterModel: string | null;
  };
  supabase: {
    ok: boolean | null;
    fixturesCount: number | null;
    error: string | null;
  };
};

function isoToday() {
  const d = new Date();
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
      </div>
    </div>
  );
}

