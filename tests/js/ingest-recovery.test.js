import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeD1 } from "./fake_d1.js";
import { ingest } from "../../functions/api/ingest.js";

const item = (n, extra = {}) => ({
  url_canonical: `https://example.com/${n}`, url_original: `https://example.com/${n}`,
  title: `Article ${n}`, outlet: "Example", source_feed: "Example", tier: "trade", lang: "en",
  published_at: "2026-09-25T01:00:00Z", score: 5, rss_summary: "Summary",
  cluster_ref: "new:1", added_by: "bot", tags: [], ...extra,
});

test("retry after a lost response recovers the cluster for later batches", async () => {
  const db = fakeD1();
  try {
    // The database commits, but the caller never receives the first response.
    await ingest(db, null, [item(1), item(2)], true, "run");
    const original = db.raw.prepare("SELECT cluster_id FROM news_items LIMIT 1").get().cluster_id;
    const retry = await ingest(db, null, [item(1), item(2)], true, "run");
    assert.equal(retry.inserted, 0);
    assert.equal(retry.duplicates, 2);
    assert.equal(retry.clusters["new:1"], original);
    await ingest(db, null, [item(3, { cluster_ref: retry.clusters["new:1"] })], true, "run");
    assert.equal(db.raw.prepare("SELECT COUNT(*) AS n FROM clusters").get().n, 1);
    assert.equal(db.raw.prepare("SELECT item_count FROM clusters").get().item_count, 3);
  } finally { db.raw.close(); }
});

test("a mixed retry joins unseen articles to the already committed cluster", async () => {
  const db = fakeD1();
  try {
    const first = await ingest(db, null, [item(1)], true, "run");
    const retry = await ingest(db, null, [item(1), item(2)], true, "run");
    assert.equal(retry.clusters["new:1"], first.clusters["new:1"]);
    assert.equal(retry.inserted, 1);
    assert.equal(retry.duplicates, 1);
    assert.equal(db.raw.prepare("SELECT COUNT(*) AS n FROM clusters").get().n, 1);
    assert.equal(db.raw.prepare("SELECT item_count FROM clusters").get().item_count, 2);
  } finally { db.raw.close(); }
});
