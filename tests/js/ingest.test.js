import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeD1, brokenD1 } from "./fake_d1.js";
import { onRequestPost } from "../../functions/api/ingest.js";
import { validateItem } from "../../functions/_ingest.js";
import { parseSummary } from "../../functions/_ai.js";

const TOKEN = "t0ken";
const okAI = { run: async () => ({ response: '{"title_zh": "中文標題", "summary": "穩定幣結算摘要內容。"}' }) };
const badAI = { run: async () => { throw new Error("AI down"); } };

function item(n, extra = {}) {
  return {
    url_canonical: `https://ex.com/${n}`, url_original: `https://ex.com/${n}?utm_source=x`, url_resolved: 1,
    title: `Title ${n}`, outlet: "CoinDesk", source_feed: "CoinDesk", tier: "trade", lang: "en",
    published_at: "2026-09-25T01:00:00Z", score: 5, rss_summary: "RSS summary", content: "",
    cluster_ref: "new:1", added_by: "bot", tags: [{ kind: "topic", key: "RWA" }], ...extra,
  };
}

async function post(env, body, token = TOKEN) {
  const request = new Request("https://site/api/ingest", {
    method: "POST", headers: { "x-ingest-token": token, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const res = await onRequestPost({ request, env });
  return { status: res.status, body: await res.json() };
}

const rows = (db, sql, ...a) => db.raw.prepare(sql).all(...a).map((r) => ({ ...r }));

test("token 錯誤或伺服器未設定都回 403", async () => {
  const DB = fakeD1();
  assert.equal((await post({ DB, INGEST_TOKEN: TOKEN }, { items: [item(1)] }, "wrong")).status, 403);
  assert.equal((await post({ DB }, { items: [item(1)] })).status, 403);
});

test("批次大小限制 1–10", async () => {
  const env = { DB: fakeD1(), INGEST_TOKEN: TOKEN };
  assert.equal((await post(env, { items: [] })).status, 400);
  const eleven = Array.from({ length: 11 }, (_, i) => item(i));
  assert.equal((await post(env, { items: eleven })).status, 400);
});

test("寫入新聞、AI 摘要、分組、標記、ingest_log 與 FTS", async () => {
  const DB = fakeD1();
  const r = await post({ DB, INGEST_TOKEN: TOKEN, AI: okAI },
    { run_id: "run1", items: [item(1, { score: 3 }), item(2, { score: 9 })] });
  assert.equal(r.status, 200);
  assert.deepEqual({ ...r.body, clusters: undefined },
    { inserted: 2, duplicates: 0, ai_failed: 0, errors: [], clusters: undefined });
  const cid = r.body.clusters["new:1"];
  const news = rows(DB, "SELECT title_zh, summary, summary_by, cluster_id FROM news_items ORDER BY id");
  assert.deepEqual(news[0], { title_zh: "中文標題", summary: "穩定幣結算摘要內容。", summary_by: "ai", cluster_id: cid });
  const [c] = rows(DB, "SELECT item_count, lead_item_id, first_seen FROM clusters WHERE id = ?", cid);
  assert.equal(c.item_count, 2);
  assert.equal(c.lead_item_id, 2);                       // 分數 9 的那則
  assert.equal(c.first_seen, "2026-09-25T01:00:00.000Z");
  assert.equal(rows(DB, "SELECT * FROM news_tags").length, 2);
  assert.equal(rows(DB, "SELECT run_id, received, inserted FROM ingest_log")[0].inserted, 2);
  assert.equal(rows(DB, "SELECT rowid FROM news_fts WHERE news_fts MATCH ?", "穩定幣").length, 2);
});

test("AI 失敗退回 RSS 摘要，仍然入庫", async () => {
  const DB = fakeD1();
  const r = await post({ DB, INGEST_TOKEN: TOKEN, AI: badAI }, { items: [item(1)] });
  assert.equal(r.body.inserted, 1);
  assert.equal(r.body.ai_failed, 1);
  assert.deepEqual(rows(DB, "SELECT summary, summary_by, title_zh FROM news_items")[0],
    { summary: "RSS summary", summary_by: "rss", title_zh: null });
});

test("skip_ai 不呼叫 AI；沒綁 AI 算失敗但照樣入庫", async () => {
  let called = false;
  const spyAI = { run: async () => { called = true; return {}; } };
  const r = await post({ DB: fakeD1(), INGEST_TOKEN: TOKEN, AI: spyAI }, { skip_ai: true, items: [item(1)] });
  assert.equal(called, false);
  assert.equal(r.body.ai_failed, 0);
  const r2 = await post({ DB: fakeD1(), INGEST_TOKEN: TOKEN }, { items: [item(1)] });
  assert.deepEqual([r2.body.inserted, r2.body.ai_failed], [1, 1]);
});

test("重複網址（資料庫已有、同批重複）算 duplicates；全重複時不開空分組", async () => {
  const DB = fakeD1();
  const env = { DB, INGEST_TOKEN: TOKEN, AI: okAI };
  const first = await post(env, { items: [item(1)] });
  const r = await post(env, { items: [item(1), item(2, { cluster_ref: "new:2" }), item(2, { cluster_ref: "new:2" })] });
  assert.deepEqual([r.body.inserted, r.body.duplicates], [1, 2]);
  assert.equal(r.body.clusters["new:1"], first.body.clusters["new:1"]); // 重複不開組，仍回傳對照
  assert.ok(r.body.clusters["new:2"]);
  assert.equal(rows(DB, "SELECT COUNT(*) AS n FROM clusters")[0].n, 2);
});

test("併入既有分組會更新篇數；指向不存在的分組改開新組", async () => {
  const DB = fakeD1();
  const env = { DB, INGEST_TOKEN: TOKEN, AI: okAI };
  const cid = (await post(env, { items: [item(1)] })).body.clusters["new:1"];
  await post(env, { items: [item(2, { cluster_ref: cid })] });
  assert.equal(rows(DB, "SELECT item_count FROM clusters WHERE id = ?", cid)[0].item_count, 2);
  await post(env, { items: [item(3, { cluster_ref: 999 })] });
  const [n3] = rows(DB, "SELECT cluster_id FROM news_items WHERE url_canonical = 'https://ex.com/3'");
  assert.notEqual(n3.cluster_id, 999);
  assert.equal(rows(DB, "SELECT item_count FROM clusters WHERE id = ?", n3.cluster_id)[0].item_count, 1);
});

test("單筆不合格只回報該筆，其餘照寫", async () => {
  const DB = fakeD1();
  const r = await post({ DB, INGEST_TOKEN: TOKEN, AI: okAI },
    { items: [item(1, { url_canonical: "javascript:alert(1)" }), item(2)] });
  assert.equal(r.body.inserted, 1);
  assert.deepEqual(r.body.errors, [{ index: 0, url: "javascript:alert(1)", error: "url_canonical 不正確" }]);
});

test("D1 故障回 503 db_unavailable", async () => {
  const r = await post({ DB: brokenD1(), INGEST_TOKEN: TOKEN }, { items: [item(1)] });
  assert.deepEqual([r.status, r.body.error], [503, "db_unavailable"]);
});

test("validateItem 擋下各種壞欄位", () => {
  const bad = [
    { tier: "manual" }, { lang: "EN" }, { score: 1.5 }, { published_at: "昨天" },
    { cluster_ref: "new:x" }, { cluster_ref: 0 }, { added_by: "manual" }, { url_resolved: 2 },
    { title: "  " }, { tags: [{ kind: "person", key: "x" }] }, { rss_summary: "x".repeat(2001) },
  ];
  for (const b of bad) assert.ok(validateItem(item(1, b)).error, JSON.stringify(b));
  assert.equal(validateItem(item(1)).item.published_at, "2026-09-25T01:00:00.000Z");
});

test("parseSummary 容忍 think 區塊、markdown 圍欄與物件回應", () => {
  const want = { title_zh: "標題", summary: "摘要" };
  assert.deepEqual(parseSummary('<think>想一想</think>{"title_zh":"標題","summary":"摘要"}'), want);
  assert.deepEqual(parseSummary('```json\n{"title_zh":"標題","summary":"摘要"}\n```'), want);
  assert.deepEqual(parseSummary({ title_zh: "標題", summary: "摘要" }), want);
  assert.equal(parseSummary("抱歉，我無法"), null);
  assert.equal(parseSummary('{"summary":"只有摘要"}'), null);
});
