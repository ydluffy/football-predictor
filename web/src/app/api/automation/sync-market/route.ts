import { NextResponse } from "next/server";
import { requireSupabaseAdmin } from "@/lib/requireSupabaseAdmin";
import { verifiedArtifactUpsert } from "@/lib/verifiedArtifactUpsert";
import { isSameMarketFixture, type MatchableFixture } from "@/lib/marketIntelMatch";

// 市场信号同步入口：把本地 movement / alignment 最新特征行写入 fixture_market_intel。
// 行按主客队名 + 北京时间开赛日期匹配到该销售日的 fixtures；匹配不上的行只计数，不报错。

type MovementInputRow = Record<string, unknown>;
type AlignmentInputRow = Record<string, unknown>;

type FixtureDbRow = MatchableFixture & {
  sporttery_match_number?: string | null;
};

function isMissingColumnError(message?: string | null) {
  return /column .* does not exist/i.test(String(message || ""));
}

function isMissingRelationError(message?: string | null) {
  const text = String(message || "");
  return /relation .* does not exist/i.test(text) || /Could not find the table .* in the schema cache/i.test(text);
}

function salesDayUtcRange(requestedDate: string) {
  const from = new Date(`${requestedDate}T00:00:00.000Z`).toISOString();
  const to = new Date(new Date(`${requestedDate}T00:00:00.000Z`).getTime() + 24 * 3600 * 1000).toISOString();
  return { from, to };
}

function text(value: unknown): string {
  return value == null ? "" : String(value).trim();
}

function nullableText(value: unknown): string | null {
  const parsed = text(value);
  return parsed === "" ? null : parsed;
}

function numeric(value: unknown): number | null {
  const raw = text(value);
  if (raw === "") return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function boolish(value: unknown): boolean {
  return text(value).toLowerCase() === "true";
}

// movement 存储 payload：与 /api/market-intel 的返回结构完全一致，前端类型零改动
function buildMovementPayload(row: MovementInputRow) {
  return {
    opening_captured_at: nullableText(row.opening_captured_at),
    latest_captured_at: nullableText(row.latest_captured_at),
    opening_home_handicap_median: numeric(row.opening_home_handicap_median),
    latest_home_handicap_median: numeric(row.latest_home_handicap_median),
    home_line_strength_delta: numeric(row.home_line_strength_delta),
    home_price_probability_delta: numeric(row.home_price_probability_delta),
    line_strength_per_hour: numeric(row.line_strength_per_hour),
    snapshot_count: numeric(row.snapshot_count) ?? 0,
    bookmaker_count: numeric(row.bookmaker_count) ?? 0,
    favorite_hot_without_line_support: boolish(row.favorite_hot_without_line_support),
    line_upgrade_without_price_support: boolish(row.line_upgrade_without_price_support),
    line_downgrade: boolish(row.line_downgrade),
    safe_for_shadow_features: boolish(row.safe_for_shadow_features),
  };
}

type AlignmentAggregate = {
  sample: AlignmentInputRow;
  outerValues: number[];
  diffValues: number[];
  deltaValues: number[];
  bookmakers: Set<string>;
  anyAligned: boolean;
  bestRow: AlignmentInputRow | null;
};

function aggregateAlignmentRows(rows: AlignmentInputRow[]) {
  const grouped = new Map<string, AlignmentAggregate>();
  for (const row of rows) {
    const matchId = text(row.match_id);
    const current = grouped.get(matchId) || {
      sample: row,
      outerValues: [],
      diffValues: [],
      deltaValues: [],
      bookmakers: new Set<string>(),
      anyAligned: false,
      bestRow: null,
    };
    const outer = numeric(row.outer_home_handicap);
    if (outer != null) current.outerValues.push(outer);
    const diff = numeric(row.sporttery_minus_outer_handicap);
    if (diff != null) current.diffValues.push(diff);
    const delta = numeric(row.time_delta_minutes);
    if (delta != null) current.deltaValues.push(delta);
    const bookmaker = nullableText(row.bookmaker_name);
    if (bookmaker) current.bookmakers.add(bookmaker);
    current.anyAligned = current.anyAligned || boolish(row.time_aligned);
    if (
      current.bestRow == null ||
      (numeric(row.time_delta_minutes) ?? Number.POSITIVE_INFINITY) <
        (numeric(current.bestRow.time_delta_minutes) ?? Number.POSITIVE_INFINITY)
    ) {
      current.bestRow = row;
    }
    grouped.set(matchId, current);
  }
  return grouped;
}

function buildAlignmentPayload(entry: AlignmentAggregate) {
  const median = (values: number[]) =>
    values.length > 0 ? values.sort((a, b) => a - b)[Math.floor(values.length / 2)] : null;
  return {
    sporttery_handicap: numeric(entry.sample.sporttery_handicap),
    outer_home_handicap_median: median(entry.outerValues),
    sporttery_minus_outer_handicap_median: median(entry.diffValues),
    aligned_bookmaker_count: entry.bookmakers.size,
    time_aligned: entry.anyAligned,
    min_time_delta_minutes: entry.deltaValues.length > 0 ? Math.min(...entry.deltaValues) : null,
    sporttery_captured_at: nullableText(entry.bestRow?.sporttery_captured_at),
    outer_captured_at: nullableText(entry.bestRow?.outer_captured_at),
  };
}

export async function POST(req: Request) {
  try {
    const { sb, response } = requireSupabaseAdmin(req);
    if (!sb) return response;

    const body = (await req.json()) as {
      sales_day?: string;
      movement_rows?: MovementInputRow[];
      alignment_rows?: AlignmentInputRow[];
      source_note?: string;
    };

    const salesDay = text(body.sales_day);
    if (!salesDay) {
      return NextResponse.json({ error: "missing sales_day" }, { status: 400 });
    }
    const movementRows = Array.isArray(body.movement_rows) ? body.movement_rows : [];
    const alignmentRows = Array.isArray(body.alignment_rows) ? body.alignment_rows : [];

    // 1) 该销售日的 fixtures（用于行匹配）
    const primaryResp = await sb
      .from("fixtures")
      .select(
        "fixture_id,utc_date,home_team_name,home_team_name_zh,away_team_name,away_team_name_zh,sporttery_match_number"
      )
      .eq("sporttery_sales_day", salesDay)
      .order("sporttery_match_number", { ascending: true });

    let fixtureRows: FixtureDbRow[] = [];
    if (primaryResp.error && isMissingColumnError(primaryResp.error.message)) {
      const { from, to } = salesDayUtcRange(salesDay);
      const fallbackResp = await sb
        .from("fixtures")
        .select("fixture_id,utc_date,home_team_name,home_team_name_zh,away_team_name,away_team_name_zh")
        .gte("utc_date", from)
        .lt("utc_date", to)
        .order("utc_date", { ascending: true });
      if (fallbackResp.error) {
        return NextResponse.json({ error: fallbackResp.error.message }, { status: 500 });
      }
      fixtureRows = (fallbackResp.data || []) as FixtureDbRow[];
    } else {
      if (primaryResp.error) {
        return NextResponse.json({ error: primaryResp.error.message }, { status: 500 });
      }
      fixtureRows = (primaryResp.data || []) as FixtureDbRow[];
    }

    // 2) movement 行匹配
    const intelByFixture = new Map<
      number,
      {
        fixture_id: number;
        sales_day: string;
        movement: Record<string, unknown> | null;
        alignment: Record<string, unknown> | null;
        movement_captured_at: string | null;
        alignment_captured_at: string | null;
        source_note: string | null;
      }
    >();
    for (const fixture of fixtureRows) {
      intelByFixture.set(fixture.fixture_id, {
        fixture_id: fixture.fixture_id,
        sales_day: salesDay,
        movement: null,
        alignment: null,
        movement_captured_at: null,
        alignment_captured_at: null,
        source_note: text(body.source_note) || null,
      });
    }

    let matchedMovement = 0;
    let unmatchedMovement = 0;
    for (const row of movementRows) {
      const fixture = fixtureRows.find((item) =>
        isSameMarketFixture(item, text(row.home_team), text(row.away_team), text(row.kickoff_at)),
      );
      if (!fixture) {
        unmatchedMovement += 1;
        continue;
      }
      const payload = buildMovementPayload(row);
      const existing = intelByFixture.get(fixture.fixture_id);
      if (existing) {
        existing.movement = payload;
        existing.movement_captured_at = payload.latest_captured_at;
      }
      matchedMovement += 1;
    }

    // 3) alignment 行按 match_id 聚合后匹配
    const grouped = aggregateAlignmentRows(alignmentRows);
    let matchedAlignment = 0;
    let unmatchedAlignment = 0;
    for (const entry of grouped.values()) {
      const fixture = fixtureRows.find((item) =>
        isSameMarketFixture(
          item,
          text(entry.sample.home_team),
          text(entry.sample.away_team),
          text(entry.sample.kickoff_at),
        ),
      );
      if (!fixture) {
        unmatchedAlignment += 1;
        continue;
      }
      const payload = buildAlignmentPayload(entry);
      const existing = intelByFixture.get(fixture.fixture_id);
      if (existing) {
        existing.alignment = payload;
        existing.alignment_captured_at = payload.outer_captured_at;
      }
      matchedAlignment += 1;
    }

    // 4) 只写有内容的行（纯 movement 或纯 alignment 也算）
    const rows = [...intelByFixture.values()].filter((row) => row.movement || row.alignment);
    const upsertResult = await verifiedArtifactUpsert(sb, "fixture_market_intel", rows, "fixture_id");
    if (upsertResult.error) {
      if (isMissingRelationError(upsertResult.error.message)) {
        return NextResponse.json(
          { error: "table_missing:fixture_market_intel（请先执行 supabase/migrations/add_fixture_market_intel.sql）" },
          { status: 500 },
        );
      }
      return NextResponse.json({ error: upsertResult.error.message, table: "fixture_market_intel" }, { status: 500 });
    }

    return NextResponse.json({
      verified: true,
      persisted_market_intel: upsertResult.count,
      fixture_count: fixtureRows.length,
      matched_movement: matchedMovement,
      unmatched_movement: unmatchedMovement,
      matched_alignment: matchedAlignment,
      unmatched_alignment: unmatchedAlignment,
      movement_rows_received: movementRows.length,
      alignment_rows_received: alignmentRows.length,
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}
