import { NextResponse } from "next/server";

type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

function todayIsoDate() {
  const d = new Date();
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function openRouterChat(messages: any[], tools?: any[]) {
  const apiKey = process.env.OPENROUTER_API_KEY || process.env.OPEN_ROUTER_API_KEY;
  const model = process.env.OPENROUTER_MODEL || "deepseek/deepseek-chat";
  if (!apiKey) throw new Error("missing OPENROUTER_API_KEY");

  const payload: any = { model, messages };
  if (tools) payload.tools = tools;

  const resp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const raw = await resp.text();
  if (!resp.ok) throw new Error(`openrouter_http ${resp.status}: ${raw.slice(0, 800)}`);
  const json = JSON.parse(raw);
  const message = json?.choices?.[0]?.message || {};
  return { content: message.content || "", tool_calls: message.tool_calls || [] };
}

export async function POST(req: Request) {
  try {
    const body = (await req.json().catch(() => ({}))) as { messages?: ChatMessage[] };
    const incoming = body.messages || [];
    const sys =
      "你是AI球赛预测助手。你必须基于工具返回的真实数据回答，禁止编造具体赛程/伤停/赔率。\n" +
      "输出尽量使用 Markdown（表格/列表），并用 ⚽📈💡 等图标提升可读性。";

    const msgs: any[] = [{ role: "system", content: sys }, ...incoming];

  const tools = [
    {
      type: "function",
      function: {
        name: "get_fixtures",
        description: "获取某天的比赛赛程列表",
        parameters: {
          type: "object",
          properties: { date: { type: "string", description: "YYYY-MM-DD" } },
          required: ["date"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "get_predictions",
        description: "获取某天比赛的胜平负概率预测",
        parameters: {
          type: "object",
          properties: { date: { type: "string", description: "YYYY-MM-DD" } },
          required: ["date"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "ingest_football_data",
        description: "导入某个日期范围的五大联赛比赛数据到数据库",
        parameters: {
          type: "object",
          properties: {
            date_from: { type: "string", description: "YYYY-MM-DD" },
            date_to: { type: "string", description: "YYYY-MM-DD" },
          },
          required: ["date_from", "date_to"],
        },
      },
    },
  ];

    const first = await openRouterChat(msgs, tools);
    if (!first.tool_calls?.length) {
      return NextResponse.json({ content: first.content || "" });
    }

  const toolCall = first.tool_calls[0];
  const name = toolCall?.function?.name;
  let args: any = {};
  try {
    args = JSON.parse(toolCall?.function?.arguments || "{}");
  } catch {
    args = {};
  }

  const date = args.date || todayIsoDate();
  let toolResult = "";

  if (name === "get_fixtures") {
    const r = await fetch(`${new URL(req.url).origin}/api/fixtures?date=${encodeURIComponent(date)}`, { cache: "no-store" });
    toolResult = await r.text();
  } else if (name === "get_predictions") {
    const r = await fetch(`${new URL(req.url).origin}/api/predictions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date }),
    });
    toolResult = await r.text();
  } else if (name === "ingest_football_data") {
    const dateFrom = args.date_from || date;
    const dateTo = args.date_to || date;
    const r = await fetch(
      `${new URL(req.url).origin}/api/ingest/football-data?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`,
      { method: "POST" }
    );
    toolResult = await r.text();
  } else {
    toolResult = JSON.stringify({ error: "unknown tool" });
  }

  msgs.push({ role: "assistant", content: first.content || "", tool_calls: first.tool_calls });
  msgs.push({ role: "tool", tool_call_id: toolCall.id, name, content: toolResult });

    const final = await openRouterChat(msgs);
    return NextResponse.json({ content: final.content || "" });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    const hint =
      "\n\n✅ 解决方法：去 Vercel 项目 → Settings → Environment Variables，确认已配置：" +
      "\n- SUPABASE_URL" +
      "\n- SUPABASE_SERVICE_ROLE_KEY" +
      "\n- FOOTBALL_DATA_API_KEY" +
      "\n- OPENROUTER_API_KEY" +
      "\n- OPENROUTER_MODEL（可选）" +
      "\n\n你也可以打开 /setup 页面自检。";
    return NextResponse.json({ content: `⚠️ 服务端配置未就绪：${message}${hint}` }, { status: 200 });
  }
}
