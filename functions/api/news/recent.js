// GET /api/news/recent?days=14&page=0 → 近期新聞的網址與分組，給 Actions 去重與分組用。
// header x-ingest-token 要與 INGEST_TOKEN 相符。每頁 500 筆，next_page 為 null 表示沒有下一頁。
import { json, getDB, noDB, checkToken, dbUnavailable } from "../../_lib.js";

const PAGE = 500;

export async function onRequestGet({ request, env }) {
  const denied = checkToken(request, env.INGEST_TOKEN, "x-ingest-token");
  if (denied) return denied;
  const db = getDB(env);
  if (!db) return noDB();
  const q = new URL(request.url).searchParams;
  const days = Number(q.get("days") ?? 14);
  const page = Number(q.get("page") ?? 0);
  if (!Number.isInteger(days) || days < 1 || days > 400) return json({ error: "days 須為 1–400 的整數" }, 400);
  if (!Number.isInteger(page) || page < 0) return json({ error: "page 不正確" }, 400);
  const since = new Date(Date.now() - days * 86400000).toISOString();
  try {
    const { results } = await db
      .prepare(`SELECT id, url_canonical, title, title_zh, cluster_id, published_at FROM news_items
                WHERE published_at >= ? ORDER BY id LIMIT ? OFFSET ?`)
      .bind(since, PAGE + 1, page * PAGE).all();
    return json({ items: results.slice(0, PAGE), next_page: results.length > PAGE ? page + 1 : null });
  } catch (e) {
    console.error("recent failed", e);
    return dbUnavailable();
  }
}
