import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { loadControllerState, loadDailyOverrideBySalesDay, loadTaskRegistryBySalesDay } from "@/lib/controllerArtifacts";

function asDate(text: unknown) {
  const s = String(text || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  return s;
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { sales_day?: string; sales_days?: string[] };
  const requested = (body.sales_days || (body.sales_day ? [body.sales_day] : [])).map(asDate).filter(Boolean) as string[];

  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const controllerPayload = await loadControllerState();
  if (controllerPayload) {
    const payloadAny: any = controllerPayload;
    const nextRequiredAt = payloadAny?.next_required_at ?? payloadAny?.next_required_at ?? null;
    const { error } = await sb
      .from("automation_controller_state")
      .upsert(
        {
          id: "default",
          controller_month: payloadAny?.controller_month ?? null,
          execution_environment: payloadAny?.execution_environment ?? null,
          status: payloadAny?.status ?? null,
          last_rescheduled_at: payloadAny?.last_rescheduled_at ?? null,
          last_reschedule_target: payloadAny?.last_reschedule_target ?? null,
          next_required_at: nextRequiredAt,
          payload: controllerPayload,
        } as any,
        { onConflict: "id" },
      );
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const results: Array<{ sales_day: string; override: "ok" | "missing"; registry: "ok" | "missing" }> = [];
  for (const salesDay of requested) {
    const [override, registry] = await Promise.all([
      loadDailyOverrideBySalesDay(salesDay),
      loadTaskRegistryBySalesDay(salesDay),
    ]);

    if (override) {
      const payloadAny: any = override;
      const { error } = await sb
        .from("automation_daily_overrides")
        .upsert(
          {
            sales_day: salesDay,
            requested_at: payloadAny?.requested_at ?? null,
            requested_by: payloadAny?.requested_by ?? null,
            official_confirmed_count: payloadAny?.official_confirmed_count ?? null,
            payload: override,
          } as any,
          { onConflict: "sales_day" },
        );
      if (error) return NextResponse.json({ error: error.message, sales_day: salesDay, table: "automation_daily_overrides" }, { status: 500 });
    }

    if (registry) {
      const payloadAny: any = registry;
      const { error } = await sb
        .from("automation_task_registries")
        .upsert(
          {
            sales_day: salesDay,
            registry_updated_at: payloadAny?.updated_at ?? null,
            payload: registry,
          } as any,
          { onConflict: "sales_day" },
        );
      if (error) return NextResponse.json({ error: error.message, sales_day: salesDay, table: "automation_task_registries" }, { status: 500 });
    }

    results.push({ sales_day: salesDay, override: override ? "ok" : "missing", registry: registry ? "ok" : "missing" });
  }

  return NextResponse.json({
    synced_controller_state: Boolean(controllerPayload),
    synced_sales_days: results,
  });
}
