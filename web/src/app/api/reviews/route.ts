import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { loadReviewArtifacts } from "@/lib/reviewArtifacts";

function isMissingRelationError(message?: string | null) {
  const text = String(message || "");
  return /relation .* does not exist/i.test(text) || /Could not find the table .* in the schema cache/i.test(text);
}

export async function GET() {
  try {
    const { sb } = requireSupabaseAdmin();
    if (sb) {
      const [summaryResp, planResp] = await Promise.all([
        sb
          .from("sporttery_review_summaries")
          .select("sales_day,reviewed_at,status,plans,hits,misses,stake,payout,net_profit,roi")
          .order("sales_day", { ascending: false }),
        sb
          .from("sporttery_review_plans")
          .select("sales_day,reviewed_at,plan_id,category,result,stake,payout,net_profit,roi,note")
          .order("sales_day", { ascending: false })
          .order("plan_id", { ascending: true }),
      ]);

      const summaryErr = summaryResp.error;
      const planErr = planResp.error;
      if (summaryErr && !isMissingRelationError(summaryErr.message)) {
        return NextResponse.json({ error: summaryErr.message }, { status: 500 });
      }
      if (planErr && !isMissingRelationError(planErr.message)) {
        return NextResponse.json({ error: planErr.message }, { status: 500 });
      }

      const summaries = (summaryResp.data || []) as any[];
      const plans = (planResp.data || []) as any[];
      if (summaries.length > 0 || plans.length > 0) {
        return NextResponse.json({
          summary_count: summaries.length,
          plan_count: plans.length,
          summaries,
          plans,
        });
      }
    }

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
