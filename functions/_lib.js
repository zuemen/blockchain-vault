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
