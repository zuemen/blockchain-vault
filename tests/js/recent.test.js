import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeD1, brokenD1 } from "./fake_d1.js";
import { onRequestGet } from "../../functions/api/news/recent.js";

const TOKEN = "t0ken";

async function get(env, qs, token = TOKEN) {
  const request = new Request(`https://site/api/news/recent?${qs}`, { headers: { "x-ingest-token": token } });
  const res = await onRequestGet({ request, env });
  return { status: res.status, body: await res.json() };
}

function seed(db, n, daysAgo) {
  const pub = new Date(Date.now() - daysAgo * 86400000).toISOString();
  const ins = db.raw.prepare(`INSERT INTO news_items (url_canonical, url_original, title, outlet, source_feed, tier,
    lang, published_at, fetched_at, score, added_by) VALUES (?, ?, ?, 'o', 'f', 'trade', 'en', ?, ?, 1, 'bot')`);
  for (let i = 0; i < n; i++) ins.run(`https://ex.com/${daysAgo}/${i}`, "https://ex.com", `t${i}`, pub, pub);
}

test("需要 token", async () => {
  assert.equal((await get({ DB: fakeD1(), INGEST_TOKEN: TOKEN }, "days=14", "bad")).status, 403);
});

test("只回傳時間窗內的新聞，並分頁", async () => {
  const DB = fakeD1();
  seed(DB, 501, 1);
  seed(DB, 3, 30);
  const env = { DB, INGEST_TOKEN: TOKEN };
  const p0 = await get(env, "days=14&page=0");
  assert.equal(p0.body.items.length, 500);
  assert.equal(p0.body.next_page, 1);
  assert.deepEqual(Object.keys(p0.body.items[0]),
    ["id", "url_canonical", "title", "title_zh", "cluster_id", "published_at"]);
  const p1 = await get(env, "days=14&page=1");
  assert.deepEqual([p1.body.items.length, p1.body.next_page], [1, null]);
  assert.equal((await get(env, "days=60&page=1")).body.items.length, 4);
});

test("參數檢查與 D1 故障", async () => {
  const env = { DB: fakeD1(), INGEST_TOKEN: TOKEN };
  assert.equal((await get(env, "days=0")).status, 400);
  assert.equal((await get(env, "days=abc")).status, 400);
  assert.equal((await get(env, "page=-1")).status, 400);
  assert.equal((await get({ DB: brokenD1(), INGEST_TOKEN: TOKEN }, "days=14")).status, 503);
});
