// POST /api/ingest → GitHub Actions 送來的新聞，每批最多 10 則（spec §6.4）。
// header x-ingest-token 要與環境變數 INGEST_TOKEN 相符。
// body：{ run_id, skip_ai, items: [...] }，欄位見 functions/_ingest.js。
// 回傳：{ inserted, duplicates, ai_failed, errors: [{index, url, error}], clusters: {"new:<n>": id} }
import { json, getDB, noDB, checkToken, dbUnavailable } from "../_lib.js";
import { validateItem, MAX_BATCH } from "../_ingest.js";
import { summarize } from "../_ai.js";

// 重算分組的篇數、時間範圍與代表報導（分數最高者）
const CLUSTER_REFRESH = `UPDATE clusters SET
  item_count   = (SELECT COUNT(*) FROM news_items WHERE cluster_id = ?1),
  first_seen   = COALESCE((SELECT MIN(published_at) FROM news_items WHERE cluster_id = ?1), first_seen),
  last_seen    = COALESCE((SELECT MAX(published_at) FROM news_items WHERE cluster_id = ?1), last_seen),
  lead_item_id = (SELECT id FROM news_items WHERE cluster_id = ?1 ORDER BY score DESC, id ASC LIMIT 1),
  title_zh     = (SELECT title_zh FROM news_items WHERE cluster_id = ?1 ORDER BY score DESC, id ASC LIMIT 1)
  WHERE id = ?1`;

const INSERT_ITEM = `INSERT INTO news_items (url_canonical, url_original, url_resolved, title, title_zh, outlet,
  source_feed, tier, lang, published_at, fetched_at, summary, summary_by, score, cluster_id, added_by)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (url_canonical) DO NOTHING`;

const INSERT_TAG = `INSERT OR IGNORE INTO news_tags (news_id, kind, key)
  SELECT id, ?, ? FROM news_items WHERE url_canonical = ?`;

const placeholders = (n) => Array(n).fill("?").join(",");

export async function onRequestPost({ request, env }) {
  const denied = checkToken(request, env.INGEST_TOKEN, "x-ingest-token");
  if (denied) return denied;
  const db = getDB(env);
  if (!db) return noDB();
  let data;
  try {
    data = await request.json();
  } catch {
    return json({ error: "請送 JSON" }, 400);
  }
  const items = Array.isArray(data?.items) ? data.items : null;
  if (!items || items.length === 0 || items.length > MAX_BATCH) {
    return json({ error: `items 須為 1–${MAX_BATCH} 筆的陣列` }, 400);
  }
  const runId = typeof data.run_id === "string" ? data.run_id.slice(0, 100) : null;
  try {
    return json(await ingest(db, env.AI, items, data.skip_ai === true, runId));
  } catch (e) {
    console.error("ingest failed", e);
    return dbUnavailable();
  }
}

export async function ingest(db, ai, raw, skipAI, runId) {
  const errors = [];
  const valid = [];
  raw.forEach((r, index) => {
    const v = validateItem(r);
    if (v.error) errors.push({ index, url: typeof r?.url_canonical === "string" ? r.url_canonical : null, error: v.error });
    else valid.push(v.item);
  });

  // 網址重複：資料庫已有，或同一批前面已出現。重複不算錯誤。
  const urls = [...new Set(valid.map((i) => i.url_canonical))];
  const known = new Set();
  if (urls.length) {
    const { results } = await db
      .prepare(`SELECT url_canonical FROM news_items WHERE url_canonical IN (${placeholders(urls.length)})`)
      .bind(...urls).all();
    results.forEach((r) => known.add(r.url_canonical));
  }
  const fresh = [];
  for (const it of valid) {
    if (known.has(it.url_canonical)) continue;
    known.add(it.url_canonical);
    fresh.push(it);
  }
  const duplicates = valid.length - fresh.length;

  // 指向不存在的分組：改成開一個新組，不丟掉新聞
  const numRefs = [...new Set(fresh.map((i) => i.cluster_ref).filter(Number.isInteger))];
  if (numRefs.length) {
    const { results } = await db
      .prepare(`SELECT id FROM clusters WHERE id IN (${placeholders(numRefs.length)})`)
      .bind(...numRefs).all();
    const exists = new Set(results.map((r) => r.id));
    for (const it of fresh) {
      if (Number.isInteger(it.cluster_ref) && !exists.has(it.cluster_ref)) it.cluster_ref = `missing:${it.cluster_ref}`;
    }
  }

  // 新分組：只替真的要寫入的報導開，全是重複的就不開（避免留下空分組）
  const clusters = {};
  const newRefs = [...new Set(fresh.map((i) => i.cluster_ref).filter((r) => typeof r === "string"))];
  if (newRefs.length) {
    const now = new Date().toISOString();
    const res = await db.batch(newRefs.map(() =>
      db.prepare("INSERT INTO clusters (first_seen, last_seen, item_count) VALUES (?, ?, 0) RETURNING id").bind(now, now)));
    newRefs.forEach((ref, k) => { clusters[ref] = res[k].results[0].id; });
  }
  const clusterOf = (it) => (typeof it.cluster_ref === "string" ? clusters[it.cluster_ref] : it.cluster_ref);

  // AI 摘要平行呼叫；失敗的退回 RSS 摘要，不擋入庫
  const sums = skipAI ? fresh.map(() => null) : await Promise.all(fresh.map((it) => summarize(ai, it)));
  let aiFailed = 0;
  const fetchedAt = new Date().toISOString();
  const stmts = [];
  fresh.forEach((it, k) => {
    const s = sums[k];
    if (!skipAI && !s) aiFailed++;
    const useAI = Boolean(s && s.summary);
    const summary = useAI ? s.summary : it.rss_summary || null;
    const summaryBy = useAI ? "ai" : summary ? "rss" : null;
    stmts.push(db.prepare(INSERT_ITEM).bind(
      it.url_canonical, it.url_original, it.url_resolved, it.title, s?.title_zh ?? null, it.outlet,
      it.source_feed, it.tier, it.lang, it.published_at, fetchedAt, summary, summaryBy, it.score,
      clusterOf(it), it.added_by));
    for (const t of it.tags) stmts.push(db.prepare(INSERT_TAG).bind(t.kind, t.key, it.url_canonical));
  });
  for (const id of new Set(fresh.map(clusterOf))) stmts.push(db.prepare(CLUSTER_REFRESH).bind(id));
  stmts.push(db
    .prepare("INSERT INTO ingest_log (at, run_id, received, inserted, duplicates, ai_failed, errors) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .bind(fetchedAt, runId, raw.length, fresh.length, duplicates, aiFailed, errors.length ? JSON.stringify(errors) : null));
  await db.batch(stmts);

  const newOnly = Object.fromEntries(Object.entries(clusters).filter(([k]) => k.startsWith("new:")));
  return { inserted: fresh.length, duplicates, ai_failed: aiFailed, errors, clusters: newOnly };
}
