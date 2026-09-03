import { NextResponse } from "next/server";
import { loadReviewArtifacts } from "@/lib/reviewArtifacts";

export async function GET() {
  try {
    const data = await loadReviewArtifacts(8);
    return NextResponse.json({
      summary_count: data.summaries.length,
      plan_count: data.plans.length,
      summaries: data.summaries,
      plans: data.plans,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
