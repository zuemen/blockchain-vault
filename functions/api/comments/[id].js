// DELETE /api/comments/<id> → 刪除一則留言。
// 需要 header x-admin-token 與環境變數 ADMIN_TOKEN 相符（給站長清留言用）。
import { json, getDB, noDB, safeEqual } from "../../_lib.js";

export async function onRequestDelete({ request, params, env }) {
  const expected = env.ADMIN_TOKEN;
  // 沒設 ADMIN_TOKEN 時一律拒絕，避免空字串 token 就能刪
  if (!expected) return json({ error: "伺服器未設定 ADMIN_TOKEN" }, 403);
  const given = request.headers.get("x-admin-token") || "";
  if (!safeEqual(given, expected)) return json({ error: "token 不正確" }, 403);

  const db = getDB(env);
  if (!db) return noDB();

  const id = Number(params.id);
  if (!Number.isInteger(id) || id <= 0) return json({ error: "id 不正確" }, 400);

  const res = await db.prepare("DELETE FROM comments WHERE id = ?").bind(id).run();
  if (!res.meta.changes) return json({ error: "找不到這則留言" }, 404);
  return json({ deleted: id });
}
