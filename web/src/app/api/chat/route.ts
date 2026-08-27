import { NextResponse } from "next/server";

type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

type ToolCall = {
  id: string;
  function?: {
    name?: string;
    arguments?: string;
  };
};

type RouterMessage = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
};

type ToolDefinition = {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
};

type ToolArguments = {
  date?: string;
  date_from?: string;
  date_to?: string;
  bookmaker?: string | number;
  items?: unknown[];
};

type OpenRouterResponse = {
  choices?: Array<{
    message?: {
      content?: string | null;
      tool_calls?: ToolCall[];
    };
  }>;
};

function parseJsonObject(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
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

function addDaysIsoDate(isoDate: string, deltaDays: number) {
  const base = new Date(`${isoDate}T00:00:00+08:00`);
  const d = new Date(base.getTime() + deltaDays * 24 * 3600 * 1000);
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

function extractExplicitDate(text: string) {
  const m = text.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  return m ? m[1] : null;
}

function resolveTargetDate(userText: string, toolDate?: string) {
  const explicit = extractExplicitDate(userText);
  if (explicit) return explicit;

  const today = todayIsoDate();
  if (/(今天|今日)/.test(userText)) return today;
  if (/昨天/.test(userText)) return addDaysIsoDate(today, -1);
  if (/明天/.test(userText)) return addDaysIsoDate(today, 1);
  return toolDate || today;
}

function sanitizeAssistantOutput(text: string) {
  const lines = (text || "").split(/\r?\n/);
  const out: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      out.push(line);
      continue;
    }
    if (/tool_call_id/i.test(trimmed)) continue;
    if (/^[0-9a-f]{24,}\s*->\s*\{/.test(trimmed)) continue;
    if (/^\{\s*"date_from"\s*:\s*"\d{4}-\d{2}-\d{2}"/.test(trimmed)) continue;
    out.push(line);
  }
  return out.join("\n").trim();
}

async function openRouterChat(messages: RouterMessage[], tools?: ToolDefinition[]) {
  const apiKey = process.env.OPENROUTER_API_KEY || process.env.OPEN_ROUTER_API_KEY;
  const model = process.env.OPENROUTER_MODEL || "deepseek/deepseek-chat";
  if (!apiKey) throw new Error("missing OPENROUTER_API_KEY");

  const payload: { model: string; messages: RouterMessage[]; tools?: ToolDefinition[] } = { model, messages };
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
  const json = JSON.parse(raw) as OpenRouterResponse;
  const message = json?.choices?.[0]?.message || {};
  return { content: message.content || "", tool_calls: message.tool_calls || [] };
}

export async function POST(req: Request) {
  try {
    const body = (await req.json().catch(() => ({}))) as { messages?: ChatMessage[] };
    const incoming = body.messages || [];
    const lastUser = [...incoming].reverse().find((m) => m.role === "user")?.content || "";
    const todayCN = todayIsoDate();
    const sys =
      `你是AI球赛预测助手。今天（Asia/Shanghai）日期是 ${todayCN}。\n` +
      "你必须基于工具返回的真实数据回答，禁止编造具体赛程/伤停/赔率/球队近况/球员伤停/历史交锋等事实。\n" +
      "绝对不要输出 tool_call_id、内部 ID、原始 JSON、或者类似 'xxxxxx -> { ... }' 的调试信息。\n" +
      "当用户要求比分预测、大小球(2.5)或双方进球(BTTS)时，只能使用工具返回的模型字段进行计算/展示；没有数据就明确说明无法提供。\n" +
      "当用户说“今天/昨日/明日”但没有明确给出 YYYY-MM-DD 时，你必须使用上面的日期进行推导。\n" +
      "输出尽量使用 Markdown（表格/列表），并用 ⚽📈💡 等图标提升可读性。";

    const msgs: RouterMessage[] = [{ role: "system", content: sys }, ...incoming];

  const tools: ToolDefinition[] = [
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
    {
      type: "function",
      function: {
        name: "ingest_odds",
        description: "自动拉取指定日期的 1X2 赔率并写入数据库（需要配置 API_FOOTBALL_KEY）",
        parameters: {
          type: "object",
          properties: {
            date: { type: "string", description: "YYYY-MM-DD" },
            bookmaker: { type: "string", description: "可选，API-Football bookmaker id" },
          },
          required: ["date"],
        },
      },
    },
    {
      type: "function",
      function: {
        name: "upsert_odds",
        description: "写入或更新某些比赛的胜平负赔率（fixture_id 对应 /api/fixtures 返回的 id），随后可获取带 EV/Kelly 的预测",
        parameters: {
          type: "object",
          properties: {
            date: { type: "string", description: "YYYY-MM-DD（可选，用于随后拉取预测）" },
            items: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  fixture_id: { type: "number" },
                  odds_home: { type: "number" },
                  odds_draw: { type: "number" },
                  odds_away: { type: "number" },
                  bookmaker: { type: "string" },
                },
                required: ["fixture_id", "odds_home", "odds_draw", "odds_away"],
              },
            },
          },
          required: ["items"],
        },
      },
    },
  ];

    const first = await openRouterChat(msgs, tools);
    if (!first.tool_calls?.length) {
      return NextResponse.json({ content: sanitizeAssistantOutput(first.content || "") });
    }

  const toolCall = first.tool_calls[0];
  const name = toolCall?.function?.name;
  let toolArgs: ToolArguments = {};
  try {
    const parsed: unknown = JSON.parse(toolCall?.function?.arguments || "{}");
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      toolArgs = parsed as ToolArguments;
    }
  } catch {
    toolArgs = {};
  }

  const date = resolveTargetDate(lastUser, toolArgs.date);
  let toolResult = "";

  if (name === "get_fixtures") {
    const base = new URL(req.url).origin;
    // First attempt: requested date
    const r = await fetch(`${base}/api/fixtures?date=${encodeURIComponent(date)}`, { cache: "no-store" });
    const txt = await r.text();
    try {
      const j = parseJsonObject(txt);
      if (j?.count === 0) {
        // Auto-fallback: try yesterday then tomorrow (Asia/Shanghai)
        const d = new Date(`${date}T00:00:00+08:00`);
        const y = new Date(d.getTime() - 24 * 3600 * 1000);
        const t = new Date(d.getTime() + 24 * 3600 * 1000);
        const fmt = (dt: Date) =>
          new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(dt);
        const tryDates = [fmt(y), fmt(t)];
        for (const dstr of tryDates) {
          const rr = await fetch(`${base}/api/fixtures?date=${encodeURIComponent(dstr)}`, { cache: "no-store" });
          const ttxt = await rr.text();
          try {
            const jj = parseJsonObject(ttxt);
            if (typeof jj?.count === "number" && jj.count > 0) {
              toolResult = JSON.stringify({ ...jj, fallback_used: true, requested_date: date, used_date: dstr });
              break;
            }
          } catch {
            /* ignore */
          }
        }
        if (!toolResult && j) {
          toolResult = JSON.stringify({ ...j, fallback_used: false, requested_date: date });
        }
      } else {
        toolResult = txt;
      }
    } catch {
      toolResult = txt;
    }
  } else if (name === "get_predictions") {
    const base = new URL(req.url).origin;
    const run = async (d: string) => {
      const r = await fetch(`${base}/api/predictions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: d }),
      });
      const txt = await r.text();
      return { json: parseJsonObject(txt), raw: txt };
    };

    const firstRun = await run(date);
    if (firstRun.json?.count === 0 && !extractExplicitDate(lastUser) && /(今天|今日)/.test(lastUser)) {
      const y = addDaysIsoDate(date, -1);
      const t = addDaysIsoDate(date, 1);
      const candidates = [y, t];
      let picked = firstRun;
      let used = date;
      for (const d of candidates) {
        const rr = await run(d);
        if (typeof rr.json?.count === "number" && rr.json.count > 0) {
          picked = rr;
          used = d;
          break;
        }
      }
      if (picked.json) {
        toolResult = JSON.stringify({ ...picked.json, fallback_used: used !== date, requested_date: date, used_date: used });
      } else {
        toolResult = picked.raw;
      }
    } else {
      toolResult = firstRun.json ? JSON.stringify({ ...firstRun.json, requested_date: date }) : firstRun.raw;
    }
  } else if (name === "ingest_football_data") {
    const dateFrom = toolArgs.date_from || date;
    const dateTo = toolArgs.date_to || date;
    const r = await fetch(
      `${new URL(req.url).origin}/api/ingest/football-data?date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`,
      { method: "POST" }
    );
    toolResult = await r.text();
  } else if (name === "ingest_odds") {
    const base = new URL(req.url).origin;
    const qs = new URLSearchParams({ date });
    if (toolArgs.bookmaker) qs.set("bookmaker", String(toolArgs.bookmaker));
    const r = await fetch(`${base}/api/ingest/odds?${qs.toString()}`, { method: "POST" });
    toolResult = await r.text();
  } else if (name === "upsert_odds") {
    const base = new URL(req.url).origin;
    const items = Array.isArray(toolArgs.items) ? toolArgs.items : [];
    if (!items.length) {
      toolResult = JSON.stringify({ error: "missing items[]" });
    } else {
      const ur = await fetch(`${base}/api/odds/upsert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ odds: items }),
      });
      const utxt = await ur.text();
      if (toolArgs.date || /(今天|今日|昨天|明天)/.test(lastUser)) {
        const d = resolveTargetDate(lastUser, toolArgs.date);
        const pr = await fetch(`${base}/api/predictions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ date: d }),
        });
        const ptxt = await pr.text();
        toolResult = JSON.stringify({ upsert_result: utxt, predictions: ptxt, requested_date: d });
      } else {
        toolResult = utxt;
      }
    }
  } else {
    toolResult = JSON.stringify({ error: "unknown tool" });
  }

  msgs.push({ role: "assistant", content: first.content || "", tool_calls: first.tool_calls });
  msgs.push({ role: "tool", tool_call_id: toolCall.id, name, content: toolResult });

    const final = await openRouterChat(msgs);
    return NextResponse.json({ content: sanitizeAssistantOutput(final.content || "") });
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
