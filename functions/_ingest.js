// /api/ingest 的輸入驗證（純函式，可用 node --test 測）。沒有 onRequest* 匯出，Pages 不會產生路由。
import { charLen } from "./_lib.js";

export const MAX_BATCH = 10;
const TIERS = new Set(["primary", "trade", "aggregator"]);
const ADDED_BY = new Set(["bot", "import"]);
const TAG_KINDS = new Set(["topic", "watch", "note", "jurisdiction"]);
const MAX = { url: 2048, title: 500, name: 200, rss_summary: 2000, content: 3000, tag_key: 100, tags: 40 };

const isUrl = (s) => typeof s === "string" && s.length <= MAX.url && /^https?:\/\/\S+$/i.test(s);
const text = (v, max) => (typeof v === "string" && v.trim() && charLen(v.trim()) <= max ? v.trim() : null);
const optText = (v, max) => {
  if (v === undefined || v === null || v === "") return { ok: true, value: "" };
  return typeof v === "string" && charLen(v) <= max ? { ok: true, value: v.trim() } : { ok: false };
};

// 回傳 { item } 或 { error }
export function validateItem(raw) {
  if (!raw || typeof raw !== "object") return { error: "不是物件" };
  if (!isUrl(raw.url_canonical)) return { error: "url_canonical 不正確" };
  if (!isUrl(raw.url_original)) return { error: "url_original 不正確" };
  const title = text(raw.title, MAX.title);
  if (!title) return { error: "title 不正確" };
  const outlet = text(raw.outlet, MAX.name);
  if (!outlet) return { error: "outlet 不正確" };
  const source_feed = text(raw.source_feed, MAX.name);
  if (!source_feed) return { error: "source_feed 不正確" };
  if (!TIERS.has(raw.tier)) return { error: "tier 不正確" };
  if (typeof raw.lang !== "string" || !/^[a-z]{2}$/.test(raw.lang)) return { error: "lang 不正確" };
  if (typeof raw.published_at !== "string" || Number.isNaN(Date.parse(raw.published_at))) {
    return { error: "published_at 不正確" };
  }
  if (!Number.isInteger(raw.score)) return { error: "score 必須是整數" };
  if (!ADDED_BY.has(raw.added_by)) return { error: "added_by 不正確" };
  const ref = raw.cluster_ref;
  if (!(Number.isInteger(ref) && ref > 0) && !(typeof ref === "string" && /^new:\d{1,5}$/.test(ref))) {
    return { error: "cluster_ref 不正確" };
  }
  const url_resolved = raw.url_resolved === undefined ? 1 : raw.url_resolved;
  if (url_resolved !== 0 && url_resolved !== 1) return { error: "url_resolved 須為 0 或 1" };
  const rss = optText(raw.rss_summary, MAX.rss_summary);
  if (!rss.ok) return { error: "rss_summary 過長或不是字串" };
  const content = optText(raw.content, MAX.content);
  if (!content.ok) return { error: "content 過長或不是字串" };
  const tags = raw.tags ?? [];
  if (!Array.isArray(tags) || tags.length > MAX.tags) return { error: "tags 不正確" };
  for (const t of tags) {
    if (!t || !TAG_KINDS.has(t.kind) || !text(t.key, MAX.tag_key)) return { error: "tag 不正確" };
  }
  return {
    item: {
      url_canonical: raw.url_canonical, url_original: raw.url_original, url_resolved,
      title, outlet, source_feed, tier: raw.tier, lang: raw.lang,
      published_at: new Date(raw.published_at).toISOString(),
      score: raw.score, added_by: raw.added_by, cluster_ref: ref,
      rss_summary: rss.value, content: content.value,
      tags: tags.map((t) => ({ kind: t.kind, key: t.key.trim() })),
    },
  };
}
