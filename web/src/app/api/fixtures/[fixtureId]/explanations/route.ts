import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";

type Mode = "brief" | "detailed";

export async function GET(_: Request, context: { params: Promise<{ fixtureId: string }> }) {
  try {
    const params = await context.params;
    const fixtureId = Number(params.fixtureId);
    if (!Number.isFinite(fixtureId)) return NextResponse.json({ error: "invalid fixture_id" }, { status: 400 });

    const { sb, response } = requireSupabaseAdmin();
    if (!sb) return response;
    const { data, error } = await sb
      .from("fixture_explanations")
      .select("id,fixture_id,mode,content,created_at,source")
      .eq("fixture_id", fixtureId)
      .order("created_at", { ascending: false })
      .limit(20);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ count: (data || []).length, items: data || [] });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 500 });
  }
}

export async function POST(req: Request, context: { params: Promise<{ fixtureId: string }> }) {
  try {
    const params = await context.params;
    const fixtureId = Number(params.fixtureId);
    if (!Number.isFinite(fixtureId)) return NextResponse.json({ error: "invalid fixture_id" }, { status: 400 });

    const body = (await req.json().catch(() => ({}))) as { mode?: Mode; content?: string; source?: string; meta?: unknown };
    const mode: Mode = body.mode === "detailed" ? "detailed" : "brief";
    const content = (body.content || "").trim();
    if (!content) return NextResponse.json({ error: "missing content" }, { status: 400 });

    const { sb, response } = requireSupabaseAdmin(req);
    if (!sb) return response;
    const { data, error } = await sb
      .from("fixture_explanations")
      .insert({
        fixture_id: fixtureId,
        mode,
        content,
        source: body.source || "fixture_detail",
        meta: body.meta ?? null,
      })
      .select("id,fixture_id,mode,content,created_at,source")
      .single();

    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ item: data });
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
