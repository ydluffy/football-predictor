import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { requireWorkbenchAdmin } from "@/lib/workbenchAuth";
import { competitionNameZh, formatLocalTimeFromUtc, statusZh, teamNameZhMaybe } from "@/lib/zh";
import { translateTeamNamesWithCache } from "@/lib/translateTeamNames";

type ExplainMode = "brief" | "detailed";

type FixtureRow = {
  fixture_id: number;
  competition_code: string | null;
  competition_name: string | null;
  utc_date: string | null;
  status: string | null;
  home_team_id: number | null;
  home_team_name: string | null;
  away_team_id: number | null;
  away_team_name: string | null;
  home_score: number | null;
  away_score: number | null;
};

type OpenRouterResponse = {
  choices?: Array<{
    message?: { content?: string | null };
  }>;
};

function sanitize(text: string) {
  return (text || "").replace(/\r/g, "").trim();
}

async function openRouterChat(system: string, user: string) {
  const apiKey = process.env.OPENROUTER_API_KEY || process.env.OPEN_ROUTER_API_KEY;
  const model = process.env.OPENROUTER_MODEL || "deepseek/deepseek-chat";
  if (!apiKey) throw new Error("missing OPENROUTER_API_KEY");

  const resp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    }),
  });

  const raw = await resp.text();
  if (!resp.ok) throw new Error(`openrouter_http ${resp.status}: ${raw.slice(0, 800)}`);
  const json = JSON.parse(raw) as OpenRouterResponse;
  const content = json?.choices?.[0]?.message?.content || "";
  return sanitize(content);
}

function todayIsoDate(tz = "Asia/Shanghai") {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return fmt.format(new Date());
}

export async function POST(req: Request, context: { params: Promise<{ fixtureId: string }> }) {
  const authResponse = requireWorkbenchAdmin(req);
  if (authResponse) return authResponse;
  try {
    const params = await context.params;
    const fixtureId = Number(params.fixtureId);
    if (!Number.isFinite(fixtureId)) {
      return NextResponse.json({ content: "fixture_id 无效。" }, { status: 200 });
    }

    const body = (await req.json().catch(() => ({}))) as { mode?: ExplainMode };
    const mode: ExplainMode = body.mode === "detailed" ? "detailed" : "brief";

    const { sb } = requireSupabaseAdmin(req);
    if (!sb) {
      return NextResponse.json(
        {
          content:
            "⚠️ Supabase 未配置：请先在本地 `web/.env.local` 或 Vercel 环境变量中配置 `SUPABASE_URL` 和 `SUPABASE_SERVICE_ROLE_KEY`，否则无法读取赛程/预测/快照数据。",
        },
        { status: 200 }
      );
    }
    const { data: fixtureData, error: fixtureError } = await sb
      .from("fixtures")
      .select(
        "fixture_id,competition_code,competition_name,utc_date,status,home_team_id,home_team_name,away_team_id,away_team_name,home_score,away_score",
      )
      .eq("fixture_id", fixtureId)
      .maybeSingle();

    if (fixtureError) return NextResponse.json({ content: `读取比赛信息失败：${fixtureError.message}` }, { status: 200 });
    if (!fixtureData) return NextResponse.json({ content: "未找到这场比赛。" }, { status: 200 });

    const fx = fixtureData as FixtureRow;
    const translated = await translateTeamNamesWithCache([fx.home_team_name, fx.away_team_name]);

    const fixture = {
      fixture_id: fx.fixture_id,
      competition: competitionNameZh(fx.competition_code, fx.competition_name),
      kickoff_beijing: formatLocalTimeFromUtc(fx.utc_date, "Asia/Shanghai"),
      status: fx.status,
      status_zh: statusZh(fx.status),
      home: teamNameZhMaybe(fx.home_team_name) || translated[(fx.home_team_name || "").trim()] || fx.home_team_name,
      away: teamNameZhMaybe(fx.away_team_name) || translated[(fx.away_team_name || "").trim()] || fx.away_team_name,
      score: typeof fx.home_score === "number" && typeof fx.away_score === "number" ? `${fx.home_score}-${fx.away_score}` : null,
    };

    // 复用“洞察接口”产物：赔率/预测快照/近期走势/单场复盘
    const base = new URL(req.url).origin;
    const [insightsResp, intelResp, predResp] = await Promise.all([
      fetch(`${base}/api/fixtures/${fixtureId}/insights`, { cache: "no-store" })
        .then((r) => r.json())
        .catch(() => null),
      fetch(`${base}/api/market-intel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fixtures: [{ fixture_id: fixture.fixture_id, utc_date: fx.utc_date, home_team_name: fx.home_team_name, away_team_name: fx.away_team_name, home_team_name_zh: fixture.home, away_team_name_zh: fixture.away }] }),
      })
        .then((r) => r.json())
        .catch(() => null),
      fetch(`${base}/api/predictions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fixture_ids: [fixtureId] }),
      })
        .then((r) => r.json())
        .catch(() => null),
    ]);

    const payload = {
      fixture,
      prediction: predResp?.predictions?.[0] || null,
      market_intel: intelResp?.items?.[0] || null,
      insights: insightsResp || null,
      evidence: {
        fixture_id: fixture.fixture_id,
        kickoff_beijing: fixture.kickoff_beijing,
        status_zh: fixture.status_zh,
        score: fixture.score,
        prediction_generated_at: insightsResp?.prediction_snapshot?.generated_at || null,
        prediction_as_of_date: insightsResp?.prediction_snapshot?.as_of_date || null,
        odds_1x2: insightsResp?.odds_snapshot || null,
        market_opening_captured_at: intelResp?.items?.[0]?.movement?.opening_captured_at || null,
        market_latest_captured_at: intelResp?.items?.[0]?.movement?.latest_captured_at || null,
        sporttery_captured_at: intelResp?.items?.[0]?.alignment?.sporttery_captured_at || null,
        outer_captured_at: intelResp?.items?.[0]?.alignment?.outer_captured_at || null,
        home_line_strength_delta: intelResp?.items?.[0]?.movement?.home_line_strength_delta ?? null,
        sporttery_minus_outer_handicap_median: intelResp?.items?.[0]?.alignment?.sporttery_minus_outer_handicap_median ?? null,
      },
    };

    const sys =
      `你是“球赛预测工作台”的单场解读助手。今天（北京时间）是 ${todayIsoDate("Asia/Shanghai")}。\n` +
      "你只能基于用户提供的 JSON 数据做解读，禁止编造任何事实（如伤停、首发、临场情报、球队近况新闻、真实盘口来源等）。\n" +
      "如果某项数据为 null/缺失，就明确写“暂无数据”。\n" +
      "输出必须是中文 Markdown，避免输出原始 JSON、调试信息或代码。\n" +
      "不要使用表情符号，不要输出免责声明以外的冗长废话。\n";

    const templateBrief =
      "请严格按以下模板输出（不要增删标题）：\n" +
      "## 一句话结论\n" +
      "（1 行）\n\n" +
      "## 要点\n" +
      "- 模型倾向：\n" +
      "- 置信度：\n" +
      "- 市场信号：\n" +
      "- 赔率/EV/Kelly：\n" +
      "- 近期走势：\n" +
      "- 风险与不确定性：\n\n" +
      "## 证据清单\n" +
      "- （列出 5-10 条可引用的“时间点/数值/字段名”，例如 kickoff、预测生成时间、盘口采集时间、内外盘差值等）\n\n" +
      "## 下一步建议\n" +
      "（3 条以内，包含“建议点哪里看什么”）\n";

    const templateDetailed =
      "请严格按以下模板输出（不要增删标题）：\n" +
      "## 关键信息\n" +
      "- 比赛：\n" +
      "- 时间：\n" +
      "- 状态/比分：\n\n" +
      "## 模型结论\n" +
      "- 胜平负：\n" +
      "- 置信度与λ：\n" +
      "- 关键因素：\n\n" +
      "## 市场信号解读\n" +
      "- 标签：\n" +
      "- 盘口强度/内外盘差：\n" +
      "- 时间对齐：\n\n" +
      "## 赔率与EV/Kelly\n" +
      "- 当前赔率：\n" +
      "- EV：\n" +
      "- Kelly：\n\n" +
      "## 近期走势\n" +
      "- 主队近 5 场：\n" +
      "- 客队近 5 场：\n\n" +
      "## 单场复盘（若已完赛）\n" +
      "- 实际 vs 预测：\n" +
      "- 单场 logloss：\n\n" +
      "## 证据清单\n" +
      "- 要求：列出 8-15 条“字段名 + 值 + 时间/来源说明（若有）”，必须来自 evidence / payload，不要编造。\n\n" +
      "## 风险与不确定性\n" +
      "- 数据缺失：\n" +
      "- 模型局限：\n\n" +
      "## 建议动作\n" +
      "1. \n" +
      "2. \n" +
      "3. \n";

    const instructions = mode === "detailed" ? templateDetailed : templateBrief;

    const user =
      `${instructions}\n\n` +
      "下面是可用数据（JSON）：\n" +
      "```json\n" +
      JSON.stringify(payload, null, 2) +
      "\n```\n";

    const content = await openRouterChat(sys, user);
    return NextResponse.json({ content });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    const hint =
      "\n\n✅ 解决方法：去 Vercel 项目 → Settings → Environment Variables，确认已配置 OPENROUTER_API_KEY（以及可选 OPENROUTER_MODEL）。";
    return NextResponse.json({ content: `⚠️ 解读服务未就绪：${message}${hint}` }, { status: 200 });
  }
}
