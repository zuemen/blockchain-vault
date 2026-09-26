import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeD1 } from "./fake_d1.js";
import { ingest } from "../../functions/api/ingest.js";

function item(n, extra = {}) {
  return {
    url_canonical: `https://ex.com/${n}`, url_original: `https://ex.com/${n}`, url_resolved: 1,
    title: `Title ${n}`, outlet: "CoinDesk", source_feed: "CoinDesk", tier: "trade", lang: "en",
    published_at: "2026-09-25T01:00:00Z", score: 5, rss_summary: "RSS", cluster_ref: "new:1",
    added_by: "bot", tags: [{ kind: "topic", key: "RWA" }], ...extra,
  };
}

const count = (db, table) => db.raw.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n;

// 寫入新聞的那一批失敗（例如 D1 中途斷線）；其他批次照常。
function failNewsWrite(db) {
  const batch = db.batch.bind(db);
  return { ...db, batch: async (stmts) => {
    if (stmts.some((s) => s.sql.includes("INSERT INTO news_items"))) throw new Error("simulated write failure");
    return batch(stmts);
  } };
}

test("寫入新聞失敗時不留下空分組；重跑後正常寫入且只有一個分組", async () => {
  const db = fakeD1();
  await assert.rejects(ingest(failNewsWrite(db), null, [item(1)], true, "failure"), /simulated write failure/);
  assert.equal(count(db, "clusters"), 0);
  assert.equal(count(db, "news_items"), 0);

  const r = await ingest(db, null, [item(1)], true, "rerun");
  assert.equal(r.inserted, 1);
  assert.equal(count(db, "clusters"), 1);
  assert.equal(db.raw.prepare("SELECT item_count FROM clusters").get().item_count, 1);
});

test("讀完分組編號後有其他寫入者搶先建分組：整批失敗、不動既有資料，重試成功", async () => {
  const db = fakeD1();
  await ingest(db, null, [item(1)], true, "seed");
  const racing = { ...db, batch: async (stmts) => {
    db.raw.prepare("INSERT INTO clusters (first_seen, last_seen, item_count) VALUES ('t', 't', 0)").run();
    return db.batch(stmts);
  } };
  await assert.rejects(ingest(racing, null, [item(2)], true, "race"));
  assert.equal(count(db, "news_items"), 1);                        // 既有新聞還在
  assert.equal(db.raw.prepare("SELECT COUNT(*) AS n FROM clusters WHERE item_count = 0").get().n, 1); // 只有搶先者那一筆

  const r = await ingest(db, null, [item(2)], true, "retry");
  assert.equal(r.inserted, 1);
  assert.equal(count(db, "news_items"), 2);
});
