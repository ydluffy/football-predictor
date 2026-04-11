import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { normalizeName } from "@/lib/zh";

type TranslationRow = {
  name_norm: string;
  name_original: string | null;
  name_zh: string;
  provider: string | null;
};

function isProbablyChinese(s: string) {
  return /[\u4e00-\u9fff]/.test(s);
}

async function openRouterTranslate(names: string[]) {
  const apiKey = process.env.OPENROUTER_API_KEY || process.env.OPEN_ROUTER_API_KEY;
  const model = process.env.OPENROUTER_MODEL || "deepseek/deepseek-chat";
  if (!apiKey) throw new Error("missing OPENROUTER_API_KEY");

  const system =
    "你是体育数据产品里的翻译器。任务：把足球俱乐部/国家队名称翻译成简体中文的常见叫法。" +
    "只输出 JSON（不要 Markdown），格式必须是 {\"translations\": {\"原文\": \"中文\"}}。" +
    "如果原文已经是中文，原样返回。不要添加额外解释。";

  const user = `需要翻译的名称列表：\n${names.map((n) => `- ${n}`).join("\n")}`;

  const resp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    }),
  });

  const raw = await resp.text();
  if (!resp.ok) throw new Error(`openrouter_http ${resp.status}: ${raw.slice(0, 300)}`);
  const json = JSON.parse(raw);
  const content = json?.choices?.[0]?.message?.content || "";

  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  const trimmed = start >= 0 && end >= 0 ? content.slice(start, end + 1) : content;
  const parsed = JSON.parse(trimmed);
  const translations = parsed?.translations;
  if (!translations || typeof translations !== "object") throw new Error("invalid translation json");
  return translations as Record<string, string>;
}

export async function translateTeamNamesWithCache(names: Array<string | null | undefined>) {
  const uniqueOriginal = Array.from(
    new Set(
      names
        .map((n) => (n || "").trim())
        .filter((n) => n.length > 0)
    )
  );

  const map: Record<string, string> = {};
  const missing: string[] = [];

  for (const n of uniqueOriginal) {
    if (isProbablyChinese(n)) map[n] = n;
  }

  const sb = supabaseAdmin();
  const norms = uniqueOriginal.map((n) => normalizeName(n));
  if (norms.length) {
    const { data } = await sb.from("team_name_translations").select("name_norm,name_zh,name_original,provider").in("name_norm", norms);
    for (const r of (data || []) as TranslationRow[]) {
      const orig = uniqueOriginal.find((x) => normalizeName(x) === r.name_norm);
      if (orig) map[orig] = r.name_zh;
    }
  }

  for (const n of uniqueOriginal) {
    if (map[n]) continue;
    missing.push(n);
  }

  const toTranslate = missing.slice(0, 20);
  if (toTranslate.length) {
    let translated: Record<string, string> = {};
    try {
      translated = await openRouterTranslate(toTranslate);
    } catch {
      translated = {};
    }

    const upserts: Array<{ name_norm: string; name_original: string; name_zh: string; provider: string }> = [];
    for (const orig of toTranslate) {
      const zh = (translated[orig] || "").trim();
      if (!zh) continue;
      map[orig] = zh;
      upserts.push({
        name_norm: normalizeName(orig),
        name_original: orig,
        name_zh: zh,
        provider: "openrouter",
      });
    }
    if (upserts.length) {
      await sb.from("team_name_translations").upsert(upserts, { onConflict: "name_norm" });
    }
  }

  return map;
}

