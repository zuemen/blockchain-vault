-- 留言資料表（Cloudflare D1）。在 D1 資料庫的 Console 貼上執行一次即可。
-- 不記錄 IP 或任何識別資訊：朋友圈使用，少存個資。
CREATE TABLE IF NOT EXISTS comments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  slug       TEXT NOT NULL,        -- 筆記的 slug（檔名去掉 .md）
  name       TEXT,                 -- 暱稱，可空（前端顯示「訪客」）
  body       TEXT NOT NULL,        -- 內容，上限 1000 字（由 API 檢查）
  rating     INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),  -- 對「判讀」的評分，可空
  created_at TEXT NOT NULL         -- ISO 8601（UTC）
);
CREATE INDEX IF NOT EXISTS idx_comments_slug ON comments (slug);
