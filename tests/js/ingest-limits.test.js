import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeD1 } from "./fake_d1.js";
import { ingest } from "../../functions/api/ingest.js";

test("ten articles with forty tags each fit the free-tier query and parameter budgets", async () => {
  const db = fakeD1();
  let queries = 0;
  const check = (stmt) => ({
    bind(...args) {
      assert.ok(args.length <= 100, `bound parameters: ${args.length}`);
      return check(stmt.bind(...args));
    },
    all() { queries++; return stmt.all(); },
    stmt,
  });
  const counted = {
    prepare: (sql) => check(db.prepare(sql)),
    batch(stmts) {
      queries += stmts.length;
      return db.batch(stmts.map((s) => s.stmt));
    },
  };
  const items = Array.from({ length: 10 }, (_, n) => ({
    url_canonical: `https://example.com/${n}`, url_original: `https://example.com/${n}`,
    title: `Article ${n}`, outlet: "Example", source_feed: "Example", tier: "trade", lang: "en",
    published_at: "2026-09-25T01:00:00Z", score: 5, rss_summary: "Summary",
    cluster_ref: `new:${n}`, added_by: "bot",
    tags: Array.from({ length: 40 }, (_, k) => ({ kind: "topic", key: `分類 '${k}` })),
  }));
  try {
    const result = await ingest(counted, null, items, true, "budget");
    assert.equal(result.inserted, 10);
    assert.equal(db.raw.prepare("SELECT COUNT(*) AS n FROM news_tags").get().n, 400);
    // Reserve room for the ten optional AI calls within the 50-subrequest limit.
    assert.ok(queries <= 40, `${queries} D1 statements leave no room for AI`);
  } finally { db.raw.close(); }
});
