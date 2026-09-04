import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";

export async function POST(req: Request) {
  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const body = (await req.json().catch(() => ({}))) as { active_config_id?: string | null };
  const active_config_id = body.active_config_id || null;

  if (active_config_id) {
    const { data: exists } = await sb.from("llm_provider_configs").select("id").eq("id", active_config_id).maybeSingle();
    if (!exists) return NextResponse.json({ error: "config not found" }, { status: 404 });
  }

  const { error } = await sb.from("llm_runtime_settings").upsert({ id: "default", active_config_id });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
