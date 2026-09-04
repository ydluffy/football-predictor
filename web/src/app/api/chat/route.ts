import { NextResponse } from "next/server";
import { loadActiveLlmConfig } from "@/lib/llmConfig";
import { buildChatCompletionsUrl } from "@/lib/llmHttp";
import { requireWorkbenchAdmin } from "@/lib/workbenchAuth";

type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

type RouterMessage = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
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

type OpenAIChatResponse = {
  choices?: Array<{ message?: { content?: string | null } }>;
};

async function openAiCompatibleChat(
  cfg: { provider?: string; baseUrl: string; apiKey: string; model: string },
  messages: RouterMessage[]
) {
  const url = buildChatCompletionsUrl(cfg.provider, cfg.baseUrl);
  if (!url) throw new Error("invalid base_url");
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cfg.apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: cfg.model,
      messages,
      temperature: 0.2,
      max_tokens: 900,
    }),
  });
  const raw = await resp.text();
  if (!resp.ok) throw new Error(`llm_http ${resp.status}: ${raw.slice(0, 800)}`);
  const json = JSON.parse(raw) as OpenAIChatResponse;
  return (json?.choices?.[0]?.message?.content || "").trim();
}

function pickKeys(obj: any, keys: string[]) {
  const out: any = {};
  for (const k of keys) out[k] = obj?.[k];
  return out;
}

function compactToolData(toolData: any) {
  // 避免把过大 JSON 塞进提示词
  if (!toolData || typeof toolData !== "object") return toolData;

  const fx = toolData.fixtures;
  const compact: any = { ...toolData };
  if (Array.isArray(fx)) {
    compact.fixtures = fx.slice(0, 20).map((r) =>
      pickKeys(r, ["fixture_id", "competition_name", "competition_code", "utc_date", "status", "home_team_name", "away_team_name"])
    );
    compact.fixtures_truncated = fx.length > 20;
  }

  const preds = toolData.predictions;
  if (Array.isArray(preds)) {
    compact.predictions = preds.slice(0, 20).map((r) =>
      pickKeys(r, ["fixture_id", "home_team_name", "away_team_name", "p_home", "p_draw", "p_away", "sporttery_handicap"])
    );
    compact.predictions_truncated = preds.length > 20;
  }
  return compact;
}

function twoSectionFallback(args: {
  userText: string;
  date: string;
  controller?: any;
  fixtures?: any;
  predictions?: any;
  llmConfigured: boolean;
}) {
  const { userText, date, controller, fixtures, predictions, llmConfigured } = args;
  const bullets: string[] = [];

  // 操盘摘要
  if (controller) {
    const c = controller.controller_state || controller.controller || null;
    const planCount = controller.plan?.count ?? controller.override?.count ?? controller.override_count ?? null;
    const taskCount = controller.registry?.count ?? controller.tasks?.count ?? null;
    const pending = controller.registry?.pending_count ?? controller.pending ?? null;
    const failed = controller.registry?.failed_count ?? controller.failed ?? null;
    if (c?.status) bullets.push(`总控状态：${c.status}`);
    if (planCount !== null) bullets.push(`计划阶段：${planCount}`);
    if (taskCount !== null) bullets.push(`执行任务：${taskCount}`);
    if (pending !== null) bullets.push(`待跑：${pending}`);
    if (failed) bullets.push(`失败：${failed}（建议展开细节查看 last_error）`);
  }
  if (fixtures && typeof fixtures.count === "number") bullets.push(`今日赛程：${fixtures.count} 场（销售日/日期：${date}）`);
  if (predictions && typeof predictions.count === "number") bullets.push(`今日预测：${predictions.count} 场（若为 0，建议先同步或检查产物是否生成）`);
  if (!bullets.length) bullets.push(`已收到问题：${userText}（数据不足/需同步/需补采）`);

  const improve: string[] = [];
  if (!llmConfigured) {
    improve.push("未配置大模型（BYOK）：可在页面“模型配置”里添加国内模型的 `base_url/model/api_key` 后启用。");
  }
  improve.push("球赛相关回答会优先使用系统数据：建议先点“同步该日/同步今日+昨日”，确保 override/registry/赛程/预测已入库。");
  improve.push("若你问的是“你能看到项目内容吗/系统状态吗”这类问题：我会尝试读取总控状态与当日销售日上下文；如果仍为空，说明链路确实未产出或未入库。");
  improve.push("建议把“快照批次（pipeline_run_id）+ generated_at + source + model_version”写入所有数据表，保证可追溯与多 Agent 不冲突。");

  return (
    `### 操盘摘要\n` +
    bullets.map((b) => `- ${b}`).join("\n") +
    `\n\n### 系统改进建议\n` +
    improve.map((b) => `- ${b}`).join("\n")
  );
}

export async function POST(req: Request) {
  const authResponse = requireWorkbenchAdmin(req);
  if (authResponse) return authResponse;
  try {
    const body = (await req.json().catch(() => ({}))) as {
      messages?: ChatMessage[];
      context?: { page?: string; sales_day?: string; repo_snapshot_id?: string; pipeline_run_id?: string };
    };
    const incoming = body.messages || [];
    const lastUser = [...incoming].reverse().find((m) => m.role === "user")?.content || "";
    const todayCN = todayIsoDate();
    const contextSalesDay = typeof body.context?.sales_day === "string" ? body.context?.sales_day : undefined;
    const date = resolveTargetDate(lastUser, contextSalesDay);

    const base = new URL(req.url).origin;

    // Router：球赛相关 -> 系统数据优先
    const controllerContext = String(body.context?.page || "").toLowerCase() === "controller";
    const needController =
      controllerContext ||
      /(总控|计划|执行|hard_lock|风险|override|registry|调度|同步)/i.test(lastUser) ||
      /(项目|系统|数据|能看到|看得到|状态|跑起来|配置好)/.test(lastUser);
    const needFixtures = /(有哪些比赛|今天.*比赛|今日.*比赛|赛程|对阵)/.test(lastUser);
    const needPredictions = /(预测|胜平负|让球|概率|模型|比分|大小球|BTTS)/.test(lastUser);

    let controller: any = null;
    let fixtures: any = null;
    let predictions: any = null;

    if (needController) {
      const r = await fetch(`${base}/api/automation/status?sales_day=${encodeURIComponent(date)}`, { cache: "no-store" });
      controller = parseJsonObject(await r.text());
    }

    if (needFixtures) {
      const r = await fetch(`${base}/api/fixtures?date=${encodeURIComponent(date)}`, { cache: "no-store" });
      fixtures = parseJsonObject(await r.text());
    }

    if (needPredictions) {
      const r = await fetch(`${base}/api/predictions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date }),
      });
      predictions = parseJsonObject(await r.text());
    }

    const active = await loadActiveLlmConfig().catch(() => null);
    if (!active) {
      return NextResponse.json({
        content: twoSectionFallback({ userText: lastUser, date, controller, fixtures, predictions, llmConfigured: false }),
      });
    }

    const toolData = compactToolData({ controller, fixtures, predictions, date });

    const sys =
      `你是“总控助手 Agent”，今天（北京时间）日期是 ${todayCN}。\n` +
      `当前启用的大模型配置是：provider=${active.provider}，model=${active.model}。\n` +
      "当用户问“你现在是哪个模型/哪个 provider/是否已配置好模型”时：必须基于上述 provider/model 回答；如果你没有看到该字段或为空，必须回答“未知/未启用”，禁止猜测（例如禁止自称 Claude/GPT）。\n" +
      "你是用户与系统的统一交互层：允许用户自由提问，但只要涉及球赛事实/赛程/赔率/盘口/预测/复盘/总控状态，就必须严格以系统数据为准，禁止编造。\n" +
      "绝对不要输出任何原始 JSON、内部 ID、调试信息；你可以把数据转成表格/要点，但不能原样粘贴。\n" +
      "输出必须固定为两段结构（Markdown）：\n" +
      "### 操盘摘要\n" +
      "- 3-6 条要点，回答“现在该做什么/风险点/下一步动作”；若数据不足必须标注“数据不足/需同步/需补采”。\n" +
      "### 系统改进建议\n" +
      "- 3-6 条要点，回答“系统哪里可优化/数据链路哪里缺口/建议怎么改”。\n" +
      "下面是系统工具返回的结构化数据（仅供参考，不要原样输出）：\n" +
      JSON.stringify(toolData);

    const msgs: RouterMessage[] = [
      { role: "system", content: sys },
      { role: "user", content: lastUser },
    ];

    const content = await openAiCompatibleChat(
      { provider: active.provider, baseUrl: active.baseUrl, apiKey: active.apiKey, model: active.model },
      msgs
    );
    return NextResponse.json({ content: sanitizeAssistantOutput(content) });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({
      content:
        `### 操盘摘要\n` +
        `- ⚠️ 服务端异常：${message}\n` +
        `- 建议先刷新/同步一次，再重试提问。\n\n` +
        `### 系统改进建议\n` +
        `- 建议在 /api/chat 增加“调用系统接口失败原因”的结构化字段，避免前端只能看到字符串。\n` +
        `- 建议把 controller/status 全量切到 /api/automation/status，并在前端统一路径，避免 404 返回 HTML 导致 JSON 解析报错。\n`,
    });
  }
}
