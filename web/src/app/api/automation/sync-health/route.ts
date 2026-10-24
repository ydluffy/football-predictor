import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { verifiedArtifactUpsert } from "@/lib/verifiedArtifactUpsert";

// 同步健康度落点：把本地脚本每次阶段同步的结果并进 controller_state.payload.last_sync。
// 只做叠加，不覆盖 entrypoint 写入的其余 controller 字段；页面靠它回答“上次同步多久前 / 待补偿几条 / 最近为什么失败”。
export async function POST(req: Request) {
  const { sb, response } = requireSupabaseAdmin(req);
  if (!sb) return response;

  const body = (await req.json().catch(() => ({}))) as { run?: Record<string, unknown> };
  const run = body.run;
  if (!run || typeof run !== "object" || typeof run.at !== "string" || !run.at) {
    return NextResponse.json({ error: "missing run.at" }, { status: 400 });
  }

  const current = await sb.from("automation_controller_state").select("payload").eq("id", "default").maybeSingle();
  if (current.error) return NextResponse.json({ error: current.error.message }, { status: 500 });
  // 还没有 controller 行时不新建：先让同步步骤写入真实状态，健康度只作为它的叠加层。
  if (!current.data) return NextResponse.json({ verified: true, skipped: "no_controller_state_row" });

  const payload = { ...((current.data.payload as Record<string, unknown>) ?? {}), last_sync: run };
  const { error } = await verifiedArtifactUpsert(sb, "automation_controller_state", [{ id: "default", payload }], "id");
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ verified: true, at: run.at });
}
