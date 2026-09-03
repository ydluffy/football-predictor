import { NextResponse } from "next/server";
import { loadActiveLlmConfig } from "@/lib/llmConfig";
import { buildChatCompletionsUrl } from "@/lib/llmHttp";
import { requireWorkbenchAdmin } from "@/lib/workbenchAuth";

type OpenAIChatResponse = {
  choices?: Array<{ message?: { content?: string | null } }>;
};

export async function POST(req: Request) {
  const authResponse = requireWorkbenchAdmin(req);
  if (authResponse) return authResponse;
  const cfg = await loadActiveLlmConfig();
  if (!cfg) return NextResponse.json({ ok: false, error: "no active llm config" }, { status: 400 });

  const url = buildChatCompletionsUrl(cfg.provider, cfg.baseUrl);
  if (!url) return NextResponse.json({ ok: false, error: "invalid base_url" }, { status: 400 });
  const startedAt = Date.now();
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cfg.apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: cfg.model,
      messages: [
        { role: "system", content: "You are a helpful assistant." },
        { role: "user", content: "ping" },
      ],
      temperature: 0,
      max_tokens: 30,
    }),
  });

  const raw = await resp.text();
  const latency_ms = Date.now() - startedAt;
  if (!resp.ok) return NextResponse.json({ ok: false, status: resp.status, latency_ms, error: raw.slice(0, 800) }, { status: 200 });

  let json: OpenAIChatResponse | null = null;
  try {
    json = JSON.parse(raw) as OpenAIChatResponse;
  } catch {
    // ignore
  }
  const content = json?.choices?.[0]?.message?.content || "";
  return NextResponse.json({ ok: true, latency_ms, sample: String(content).slice(0, 200) });
}
