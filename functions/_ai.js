// Workers AI 摘要。沒有 onRequest* 匯出，Pages 不會產生路由。
export const MODEL = "@cf/qwen/qwen3-30b-a3b-fp8";
const SOURCE_MAX = 1500;

const SYSTEM = [
  "你是新聞摘要助理。只根據使用者提供的原文，原文沒寫的不要補。",
  '只輸出一個 JSON 物件：{"title_zh": "…", "summary": "…"}，不要輸出其他文字。',
  "title_zh：標題的繁體中文翻譯；原標題已是中文就轉成繁體。",
  "summary：2–3 句繁體中文，保留數字、日期、機構原名；原文不足以摘要就回空字串。",
  "/no_think",
].join("\n");

export function buildMessages(item) {
  const source = (item.content || item.rss_summary || "").slice(0, SOURCE_MAX);
  return [
    { role: "system", content: SYSTEM },
    { role: "user", content: `標題：${item.title}\n媒體：${item.outlet}\n原文：\n${source}` },
  ];
}

// 模型輸出 → {title_zh, summary}；格式不對回傳 null
export function parseSummary(out) {
  if (out && typeof out === "object") out = JSON.stringify(out);
  if (typeof out !== "string") return null;
  const m = out.replace(/<think>[\s\S]*?<\/think>/g, "").match(/\{[\s\S]*\}/);
  if (!m) return null;
  let o;
  try {
    o = JSON.parse(m[0]);
  } catch {
    return null;
  }
  if (typeof o.title_zh !== "string" || typeof o.summary !== "string") return null;
  return { title_zh: o.title_zh.trim().slice(0, 300) || null, summary: o.summary.trim().slice(0, 1000) };
}

// 失敗（沒綁 AI、逾時、格式不對）一律回傳 null，由呼叫端退回 RSS 摘要
export async function summarize(ai, item) {
  if (!ai) return null;
  try {
    const r = await ai.run(MODEL, { messages: buildMessages(item), max_tokens: 600, temperature: 0.2 });
    return parseSummary(r?.response ?? r?.choices?.[0]?.message?.content);
  } catch {
    return null;
  }
}
