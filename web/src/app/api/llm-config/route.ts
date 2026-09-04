import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { encryptToJson } from "@/lib/cryptoBox";
import { validateLlmBaseUrl } from "@/lib/llmHttp";

type CreateBody = {
  label: string;
  provider?: string;
  base_url: string;
  model: string;
  api_key: string;
};

export async function GET(req: Request) {
  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const { data: settings } = await sb.from("llm_runtime_settings").select("active_config_id").eq("id", "default").maybeSingle();
  const activeId = (settings as any)?.active_config_id ?? null;

  const { data, error } = await sb
    .from("llm_provider_configs")
    .select("id,label,provider,base_url,model,created_at,updated_at")
    .order("created_at", { ascending: false });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ active_config_id: activeId, configs: data || [] });
}

export async function POST(req: Request) {
  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  let body: CreateBody;
  try {
    body = (await req.json()) as CreateBody;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const label = (body.label || "").trim();
  const provider = (body.provider || "openai_compatible").trim();
  const base_url = (body.base_url || "").trim();
  const model = (body.model || "").trim();
  const api_key = (body.api_key || "").trim();

  if (!label || !base_url || !model || !api_key) {
    return NextResponse.json({ error: "missing fields (label/base_url/model/api_key)" }, { status: 400 });
  }
  const baseUrlValidation = validateLlmBaseUrl(provider, base_url);
  if (!baseUrlValidation.ok) {
    return NextResponse.json({ error: baseUrlValidation.error }, { status: 400 });
  }

  let encrypted: string;
  try {
    encrypted = encryptToJson(api_key);
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }

  const { data, error } = await sb
    .from("llm_provider_configs")
    .insert({ label, provider, base_url: baseUrlValidation.baseUrl, model, encrypted_api_key: encrypted })
    .select("id,label,provider,base_url,model,created_at,updated_at")
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  // 若尚未设置 active，则默认启用刚创建的
  const { data: settings } = await sb.from("llm_runtime_settings").select("active_config_id").eq("id", "default").maybeSingle();
  const activeId = (settings as any)?.active_config_id ?? null;
  if (!activeId && data?.id) {
    await sb.from("llm_runtime_settings").upsert({ id: "default", active_config_id: data.id });
  }

  return NextResponse.json({ config: data });
}
