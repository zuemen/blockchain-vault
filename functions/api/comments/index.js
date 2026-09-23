// GET  /api/comments?slug=<slug>  → 該篇留言，時間正序
// POST /api/comments              → 新增留言 {slug, name, body, rating}
// 朋友圈使用：不做 Turnstile、不做速率限制、不記錄 IP。
import { json, getDB, noDB, charLen, loadTitles } from "../../_lib.js";

const MAX_BODY = 1000;   // 內容上限（字）
const MAX_NAME = 40;     // 暱稱上限（字）
const MAX_SLUG = 200;

export async function onRequestGet({ request, env }) {
  const db = getDB(env);
  if (!db) return noDB();
  const slug = new URL(request.url).searchParams.get("slug");
  if (!slug) return json({ error: "缺少 slug" }, 400);

  const { results } = await db
    .prepare("SELECT id, name, body, rating, created_at FROM comments WHERE slug = ? ORDER BY created_at ASC, id ASC")
    .bind(slug)
    .all();
  return json({ comments: results });
}

export async function onRequestPost({ request, env }) {
  const db = getDB(env);
  if (!db) return noDB();

  let data;
  try {
    data = await request.json();
  } catch {
    return json({ error: "請送 JSON" }, 400);
  }

  const slug = typeof data.slug === "string" ? data.slug.trim() : "";
  const body = typeof data.body === "string" ? data.body.trim() : "";
  const nameRaw = typeof data.name === "string" ? data.name.trim() : "";
  const name = nameRaw === "" ? null : nameRaw;   // 空暱稱存 null，前端顯示「訪客」

  if (!slug || charLen(slug) > MAX_SLUG) return json({ error: "slug 不正確" }, 400);
  if (!body) return json({ error: "內容不能是空的" }, 400);
  if (charLen(body) > MAX_BODY) return json({ error: `內容上限 ${MAX_BODY} 字` }, 400);
  if (name && charLen(name) > MAX_NAME) return json({ error: `暱稱上限 ${MAX_NAME} 字` }, 400);

  // rating 可省略；有給就必須是 1–5 的整數
  let rating = null;
  if (data.rating !== undefined && data.rating !== null && data.rating !== "") {
    rating = Number(data.rating);
    if (!Number.isInteger(rating) || rating < 1 || rating > 5) {
      return json({ error: "評分須為 1–5" }, 400);
    }
  }

  // 只收網站上真的存在的筆記，避免打錯 slug 留下孤兒留言。search.json 讀不到時放行。
  const titles = await loadTitles(env, request);
  if (titles && !titles.has(slug)) return json({ error: "找不到這篇筆記" }, 404);

  const created_at = new Date().toISOString();
  const row = await db
    .prepare("INSERT INTO comments (slug, name, body, rating, created_at) VALUES (?, ?, ?, ?, ?) RETURNING id, name, body, rating, created_at")
    .bind(slug, name, body, rating, created_at)
    .first();
  return json({ comment: row }, 201);
}
