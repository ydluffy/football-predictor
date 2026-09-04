import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";
import { requireWorkbenchAdmin } from "@/lib/workbenchAuth";

type RequireResult =
  | { sb: ReturnType<typeof supabaseAdmin>; response: null }
  | { sb: null; response: NextResponse };

export function requireSupabaseAdmin(request?: Request): RequireResult {
  if (request) {
    const authResponse = requireWorkbenchAdmin(request);
    if (authResponse) return { sb: null, response: authResponse };
  }
  const hasUrl = Boolean(process.env.SUPABASE_URL);
  const hasKey = Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY);

  if (!hasUrl || !hasKey) {
    return {
      sb: null,
      response: NextResponse.json(
        {
          error:
            "Supabase 未配置：请设置 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY（本地开发建议写入 web/.env.local）",
        },
        { status: 503 }
      ),
    };
  }

  return { sb: supabaseAdmin(), response: null };
}
