import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { encryptToJson } from "@/lib/cryptoBox";
import { validateLlmBaseUrl } from "@/lib/llmHttp";

type UpdateBody = Partial<{
  label: string;
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
}>;

export async function PUT(req: Request, context: { params: Promise<{ id: string }> }) {
  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const params = await context.params;
  const id = params.id;

  const body = (await req.json().catch(() => ({}))) as UpdateBody;
  const patch: any = {};
  if (typeof body.label === "string") patch.label = body.label.trim();
  if (typeof body.provider === "string") patch.provider = body.provider.trim();
  if (typeof body.base_url === "string") {
    const validation = validateLlmBaseUrl(body.provider, body.base_url);
    if (!validation.ok) return NextResponse.json({ error: validation.error }, { status: 400 });
    patch.base_url = validation.baseUrl;
  }
  if (typeof body.model === "string") patch.model = body.model.trim();
  if (typeof body.api_key === "string" && body.api_key.trim()) { // pragma: allowlist secret
    patch.encrypted_api_key = encryptToJson(body.api_key.trim());
  }

  if (Object.keys(patch).length === 0) return NextResponse.json({ error: "no changes" }, { status: 400 });

  const { data, error } = await sb
    .from("llm_provider_configs")
    .update(patch)
    .eq("id", id)
    .select("id,label,provider,base_url,model,created_at,updated_at")
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json({ config: data });
}

export async function DELETE(req: Request, context: { params: Promise<{ id: string }> }) {
  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const params = await context.params;
  const id = params.id;

  // 如果当前 active 指向该配置，先清空
  const { data: settings } = await sb.from("llm_runtime_settings").select("active_config_id").eq("id", "default").maybeSingle();
  const activeId = (settings as any)?.active_config_id ?? null;
  if (activeId === id) {
    await sb.from("llm_runtime_settings").upsert({ id: "default", active_config_id: null });
  }

  const { error } = await sb.from("llm_provider_configs").delete().eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
