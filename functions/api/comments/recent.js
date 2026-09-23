// GET /api/comments/recent → 全站最近 10 筆（含 slug 與筆記標題），給首頁「最近留言」用
// 靜態路由 recent 的優先權高於同層的動態路由 [id]，不會被當成 id。
import { json, getDB, noDB, loadTitles } from "../../_lib.js";

export async function onRequestGet({ request, env }) {
  const db = getDB(env);
  if (!db) return noDB();

  const { results } = await db
    .prepare("SELECT id, slug, name, body, rating, created_at FROM comments ORDER BY created_at DESC, id DESC LIMIT 10")
    .all();

  // D1 只存 slug，標題從網站自己的 search.json 對照；對不到就用 slug 代替
  const titles = await loadTitles(env, request);
  const comments = results.map((c) => ({ ...c, title: titles?.get(c.slug) || c.slug }));
  return json({ comments });
}
