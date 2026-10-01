import type { supabaseAdmin } from "./supabaseAdmin";

type Row = Record<string, unknown>;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return JSON.stringify(Object.keys(value).sort().map((key) => [key, canonical((value as Row)[key])]));
  }
  return JSON.stringify(value);
}

function sameValue(key: string, a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if ((key.endsWith("_at") || key === "utc_date" || key === "last_reschedule_target") && typeof a === "string" && typeof b === "string") {
    return Number.isFinite(Date.parse(a)) && Date.parse(a) === Date.parse(b);
  }
  return canonical(a) === canonical(b);
}

export function uniqueArtifactRows(rows: Row[], keys: string[]): Row[] {
  const unique = new Map<string, Row>();
  for (const row of rows) {
    if (keys.some((key) => row[key] === undefined || row[key] === null || row[key] === "")) {
      throw new Error("missing sync identity");
    }
    const id = JSON.stringify(keys.map((key) => row[key]));
    const previous = unique.get(id);
    const stamp = (r: Row) => Date.parse(String(r.reviewed_at || r.generated_at || r.analysis_at || "")) || 0;
    if (!previous || stamp(row) >= stamp(previous)) unique.set(id, row);
  }
  return [...unique.values()];
}

/** Idempotent upsert followed by an independent database SELECT, not an HTTP-only acknowledgement. */
export async function verifiedArtifactUpsert(
  sb: ReturnType<typeof supabaseAdmin>, table: string, input: Row[], onConflict: string,
) {
  const keys = onConflict.split(",");
  const rows = uniqueArtifactRows(input, keys);
  if (!rows.length) return { error: null, verified: true, count: 0 };
  for (let start = 0; start < rows.length; start += 50) {
    const batch = rows.slice(start, start + 50);
    const { error } = await sb.from(table).upsert(batch, { onConflict });
    if (error) return { error, verified: false, count: 0 };
    // Query each full primary key to avoid API pagination hiding composite-key rows.
    for (const expected of batch) {
      let query = sb.from(table).select(Object.keys(expected).join(","));
      for (const key of keys) query = query.eq(key, expected[key]);
      const readback = await query.single();
      if (readback.error) return { error: readback.error, verified: false, count: 0 };
      const mismatch = Object.entries(expected).find(([key, value]) => !readback.data || !sameValue(key, value, (readback.data as unknown as Row)[key]));
      if (mismatch) {
        return { error: { message: `readback_mismatch:${table}:${mismatch[0]}` }, verified: false, count: 0 };
      }
    }
  }
  return { error: null, verified: true, count: rows.length };
}
