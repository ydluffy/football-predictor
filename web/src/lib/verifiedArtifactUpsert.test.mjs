import { test } from "node:test";
import assert from "node:assert/strict";
import { uniqueArtifactRows, verifiedArtifactUpsert } from "./verifiedArtifactUpsert.ts";

test("deduplicate composite keys choosing latest evidence", () => {
  const rows = uniqueArtifactRows([
    { day: "a", id: 1, reviewed_at: "2026-09-04T10:00:00Z", result: "hit" },
    { day: "a", id: 1, reviewed_at: "2026-09-03T10:00:00Z", result: "pending" },
  ], ["day", "id"]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].result, "hit");
});

function database(readback) {
  let reads = 0;
  const query = { eq: () => query, single: async () => { reads++; return { data: readback, error: null }; } };
  const db = { from: () => ({ upsert: async () => ({ error: null }), select: () => query }) };
  return { db, reads: () => reads };
}

test("readback compares values, not just successful write", async () => {
  const fake = database({ id: 1, value: "old" });
  const result = await verifiedArtifactUpsert(fake.db, "example", [{ id: 1, value: "new" }], "id");
  assert.equal(result.verified, false);
  assert.equal(fake.reads(), 1);
});

test("equivalent database timestamp and JSON order pass", async () => {
  const fake = database({ id: 1, generated_at: "2026-09-04T10:00:00Z", payload: { b: 2, a: 1 } });
  const result = await verifiedArtifactUpsert(fake.db, "example", [{ id: 1, generated_at: "2026-09-04T18:00:00+08:00", payload: { a: 1, b: 2 } }], "id");
  assert.equal(result.verified, true);
});

test("controller next wake timestamp accepts database UTC normalization", async () => {
  const fake = database({ id: "default", last_reschedule_target: "2026-09-04T13:00:00+00:00" });
  const result = await verifiedArtifactUpsert(fake.db, "controller", [{ id: "default", last_reschedule_target: "2026-09-04T21:00:00+08:00" }], "id");
  assert.equal(result.verified, true);
});
