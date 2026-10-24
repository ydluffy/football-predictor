import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";

function isMissingRelationError(message?: string | null) {
  const text = String(message || "");
  return /relation .* does not exist/i.test(text) || /Could not find the table .* in the schema cache/i.test(text);
}

export async function GET(req: Request) {
  try {
    const { sb, response } = requireSupabaseAdmin(req);
    if (!sb) return response;

    const [summaryResp, planResp] = await Promise.all([
      sb
        .from("sporttery_review_summaries")
        .select("sales_day,reviewed_at,status,plans,hits,misses,stake,payout,net_profit,roi,source_file")
        .order("sales_day", { ascending: false }),
      sb
        .from("sporttery_review_plans")
        .select("sales_day,reviewed_at,plan_id,category,result,stake,payout,net_profit,roi,note")
        .order("sales_day", { ascending: false })
        .order("plan_id", { ascending: true }),
    ]);

    if (summaryResp.error && !isMissingRelationError(summaryResp.error.message)) {
      return NextResponse.json({ error: summaryResp.error.message }, { status: 500 });
    }
    if (planResp.error && !isMissingRelationError(planResp.error.message)) {
      return NextResponse.json({ error: planResp.error.message }, { status: 500 });
    }

    const summaries = (summaryResp.data || []) as Array<{
      sales_day: string;
      reviewed_at: string | null;
      status: string;
      plans: number;
      hits: number;
      misses: number;
      stake: number;
      payout: number;
      net_profit: number;
      roi: number | null;
      source_file?: string | null;
    }>;
    const plans = (planResp.data || []) as Array<{
      sales_day: string;
      reviewed_at: string | null;
      plan_id: string;
      category: string;
      result: string;
      stake: number;
      payout: number;
      net_profit: number;
      roi: number | null;
      note: string | null;
    }>;

    const plansByDay = new Map<string, typeof plans>();
    for (const item of plans) {
      const list = plansByDay.get(item.sales_day) || [];
      list.push(item);
      plansByDay.set(item.sales_day, list);
    }

    const days = summaries.map((summary) => ({
      summary,
      plans: plansByDay.get(summary.sales_day) || [],
    }));

    const monthMap = new Map<
      string,
      {
        month: string;
        sales_day_count: number;
        plan_count: number;
        hit_count: number;
        miss_count: number;
        stake: number;
        payout: number;
        net_profit: number;
      }
    >();
    for (const item of summaries) {
      const month = item.sales_day.slice(0, 7);
      const current = monthMap.get(month) || {
        month,
        sales_day_count: 0,
        plan_count: 0,
        hit_count: 0,
        miss_count: 0,
        stake: 0,
        payout: 0,
        net_profit: 0,
      };
      current.sales_day_count += 1;
      current.plan_count += Number(item.plans || 0);
      current.hit_count += Number(item.hits || 0);
      current.miss_count += Number(item.misses || 0);
      current.stake += Number(item.stake || 0);
      current.payout += Number(item.payout || 0);
      current.net_profit += Number(item.net_profit || 0);
      monthMap.set(month, current);
    }

    const months = [...monthMap.values()]
      .map((item) => ({
        ...item,
        roi: item.stake > 0 ? item.net_profit / item.stake : null,
      }))
      .sort((a, b) => b.month.localeCompare(a.month));

    return NextResponse.json({
      summary_count: summaries.length,
      plan_count: plans.length,
      days,
      months,
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
