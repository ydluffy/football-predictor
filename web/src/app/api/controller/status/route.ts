import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";

type DbRow = {
  sales_day: string;
  payload: any;
  requested_at?: string | null;
  requested_by?: string | null;
  official_confirmed_count?: number | null;
  registry_updated_at?: string | null;
};

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const salesDay = searchParams.get("sales_day"); // YYYY-MM-DD optional

  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const controller = await sb.from("automation_controller_state").select("payload").eq("id", "default").maybeSingle();
  if (controller.error) return NextResponse.json({ error: controller.error.message }, { status: 500 });

  let overrideRow: DbRow | null = null;
  let registryRow: DbRow | null = null;
  if (salesDay) {
    const [ov, reg] = await Promise.all([
      sb
        .from("automation_daily_overrides")
        .select("sales_day,requested_at,requested_by,official_confirmed_count,payload")
        .eq("sales_day", salesDay)
        .maybeSingle(),
      sb
        .from("automation_task_registries")
        .select("sales_day,registry_updated_at,payload")
        .eq("sales_day", salesDay)
        .maybeSingle(),
    ]);

    if (ov.error) return NextResponse.json({ error: ov.error.message }, { status: 500 });
    if (reg.error) return NextResponse.json({ error: reg.error.message }, { status: 500 });

    overrideRow = (ov.data as any) || null;
    registryRow = (reg.data as any) || null;
  }

  return NextResponse.json({
    controller_state: controller.data?.payload ?? null,
    sales_day: salesDay ?? null,
    daily_override: overrideRow,
    task_registry: registryRow,
  });
}
