import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { decryptFromJson } from "@/lib/cryptoBox";

export type LlmProviderConfig = {
  id: string;
  label: string;
  provider: string;
  base_url: string;
  model: string;
  encrypted_api_key: string;
  created_at?: string;
  updated_at?: string;
};

export type ActiveLlmConfig = {
  id: string;
  label: string;
  provider: string;
  baseUrl: string;
  model: string;
  apiKey: string;
};

export async function loadActiveLlmConfig(): Promise<ActiveLlmConfig | null> {
  const { sb } = requireSupabaseAdmin();
  if (!sb) return null;

  const { data: settings, error: settingsErr } = await sb.from("llm_runtime_settings").select("active_config_id").eq("id", "default").maybeSingle();
  if (settingsErr) return null;
  const activeId = (settings as any)?.active_config_id as string | null;
  if (!activeId) return null;

  const { data: cfg, error: cfgErr } = await sb
    .from("llm_provider_configs")
    .select("id,label,provider,base_url,model,encrypted_api_key")
    .eq("id", activeId)
    .maybeSingle();
  if (cfgErr || !cfg) return null;

  const row = cfg as unknown as LlmProviderConfig;
  const apiKey = decryptFromJson(row.encrypted_api_key);
  return {
    id: row.id,
    label: row.label,
    provider: row.provider,
    baseUrl: row.base_url,
    model: row.model,
    apiKey,
  };
}
