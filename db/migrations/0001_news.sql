-- 階段 2：新聞資料表（spec §5）。可重跑：全部 IF NOT EXISTS。
-- 留言表 comments 不在這裡動，階段 3 才改成 target 欄位。
-- 執行：npx wrangler d1 execute blockchain-vault-comments --remote --file db/migrations/0001_news.sql

CREATE TABLE IF NOT EXISTS clusters (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title_zh     TEXT,
  lead_item_id INTEGER,
  first_seen   TEXT NOT NULL,
  last_seen    TEXT NOT NULL,
  item_count   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS news_items (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  url_canonical  TEXT NOT NULL UNIQUE,
  url_original   TEXT NOT NULL,
  url_resolved   INTEGER NOT NULL DEFAULT 1,
  title          TEXT NOT NULL,
  title_zh       TEXT,
  outlet         TEXT NOT NULL,
  source_feed    TEXT NOT NULL,
  tier           TEXT NOT NULL CHECK (tier IN ('primary','trade','aggregator','manual')),
  lang           TEXT NOT NULL,
  published_at   TEXT NOT NULL,
  fetched_at     TEXT NOT NULL,
  summary        TEXT,
  summary_by     TEXT CHECK (summary_by IN ('ai','rss') OR summary_by IS NULL),
  score          INTEGER NOT NULL,
  cluster_id     INTEGER REFERENCES clusters(id),
  status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','hidden')),
  added_by       TEXT NOT NULL CHECK (added_by IN ('bot','manual','import')),
  needs_annotate INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_news_pub     ON news_items (published_at);
CREATE INDEX IF NOT EXISTS idx_news_cluster ON news_items (cluster_id);

CREATE TABLE IF NOT EXISTS news_tags (
  news_id INTEGER NOT NULL REFERENCES news_items(id),
  kind    TEXT NOT NULL CHECK (kind IN ('topic','watch','note','jurisdiction')),
  key     TEXT NOT NULL,
  PRIMARY KEY (news_id, kind, key)
);
CREATE INDEX IF NOT EXISTS idx_tags_key ON news_tags (kind, key);

CREATE VIRTUAL TABLE IF NOT EXISTS news_fts USING fts5 (
  title, title_zh, summary, content='news_items', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS news_fts_ai AFTER INSERT ON news_items BEGIN
  INSERT INTO news_fts (rowid, title, title_zh, summary) VALUES (new.id, new.title, new.title_zh, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS news_fts_ad AFTER DELETE ON news_items BEGIN
  INSERT INTO news_fts (news_fts, rowid, title, title_zh, summary) VALUES ('delete', old.id, old.title, old.title_zh, old.summary);
END;
CREATE TRIGGER IF NOT EXISTS news_fts_au AFTER UPDATE ON news_items BEGIN
  INSERT INTO news_fts (news_fts, rowid, title, title_zh, summary) VALUES ('delete', old.id, old.title, old.title_zh, old.summary);
  INSERT INTO news_fts (rowid, title, title_zh, summary) VALUES (new.id, new.title, new.title_zh, new.summary);
END;

CREATE TABLE IF NOT EXISTS ingest_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  run_id     TEXT,
  received   INTEGER,
  inserted   INTEGER,
  duplicates INTEGER,
  ai_failed  INTEGER,
  errors     TEXT
);
