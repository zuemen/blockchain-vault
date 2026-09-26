// 留言 API 共用工具。這裡沒有匯出 onRequest* 處理函式，所以 Pages 不會為它產生路由。

// 回傳 JSON；留言是動態資料，一律不快取
export function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

// D1 沒綁定時給明確錯誤，而不是丟出難懂的 500
export function getDB(env) {
  return env.DB || null;
}

export const noDB = () => json({ error: "資料庫尚未綁定（Pages → Settings → Bindings 加 D1，變數名 DB）" }, 503);

// 以「字元」計長度（emoji、中文都算 1），而不是 UTF-16 code unit
export const charLen = (s) => [...s].length;

// 讀網站自己的 search.json，建立 slug → 標題 對照表。
// search.json 的 u 欄位形如 "n/<URL 編碼的 slug>.html"。讀不到就回傳空表（呼叫端退回顯示 slug）。
export async function loadTitles(env, request) {
  try {
    const url = new URL("/search.json", request.url);
    const res = env.ASSETS ? await env.ASSETS.fetch(url) : await fetch(url);
    if (!res.ok) return null;
    const idx = await res.json();
    const map = new Map();
    for (const n of idx) {
      const m = /^n\/(.+)\.html$/.exec(n.u || "");
      if (m) map.set(decodeURIComponent(m[1]), n.t);
    }
    return map;
  } catch {
    return null;
  }
}

// 固定時間比較，避免從回應時間推測 token
export function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// 驗證 header 裡的 token。通過回傳 null，否則回傳 403 回應。伺服器沒設 token 時一律拒絕。
export function checkToken(request, expected, header) {
  if (!expected) return json({ error: "伺服器未設定 token" }, 403);
  const given = request.headers.get(header) || "";
  return safeEqual(given, expected) ? null : json({ error: "token 不正確" }, 403);
}

// D1 查詢失敗時的統一回應（spec §8.3）
export const dbUnavailable = () => json({ error: "db_unavailable" }, 503);
