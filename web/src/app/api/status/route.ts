import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export async function GET() {
  const hasSupabaseUrl = Boolean(process.env.SUPABASE_URL);
  const hasSupabaseServiceRole = Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY);
  const hasFootballDataKey = Boolean(process.env.FOOTBALL_DATA_API_KEY || process.env.FOOTBALLDATA_API_KEY);
  const hasOpenRouterKey = Boolean(process.env.OPENROUTER_API_KEY || process.env.OPEN_ROUTER_API_KEY);
  const openRouterModel = process.env.OPENROUTER_MODEL || null;

  let supabaseOk: boolean | null = null;
  let fixturesCount: number | null = null;
  let supabaseError: string | null = null;
  if (hasSupabaseUrl && hasSupabaseServiceRole) {
    try {
      const sb = supabaseAdmin();
      const { count, error } = await sb.from("fixtures").select("fixture_id", { count: "exact", head: true });
      if (error) {
        supabaseOk = false;
        supabaseError = error.message;
      } else {
        supabaseOk = true;
        fixturesCount = typeof count === "number" ? count : null;
      }
    } catch (e) {
      supabaseOk = false;
      supabaseError = e instanceof Error ? e.message : String(e);
    }
  }

  return NextResponse.json({
    env: {
      hasSupabaseUrl,
      hasSupabaseServiceRole,
      hasFootballDataKey,
      hasOpenRouterKey,
      openRouterModel,
    },
    supabase: {
      ok: supabaseOk,
      fixturesCount,
      error: supabaseError,
    },
  });
}

