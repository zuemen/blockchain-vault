// 測試用的 D1：以 Node 內建 node:sqlite（含 FTS5）模擬 D1 的 prepare/bind/all/first/run/batch。
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";

const MIGRATION = new URL("../../db/migrations/0001_news.sql", import.meta.url);

class Stmt {
  constructor(db, sql, args = []) {
    this.db = db;
    this.sql = sql;
    this.args = args;
  }
  bind(...args) {
    return new Stmt(this.db, this.sql, args);
  }
  exec() {
    const results = this.db.prepare(this.sql).all(...this.args).map((r) => ({ ...r }));
    return { results, success: true, meta: {} };
  }
  async all() {
    return this.exec();
  }
  async first() {
    return this.exec().results[0] ?? null;
  }
  async run() {
    const r = this.db.prepare(this.sql).run(...this.args);
    return { success: true, meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
  }
}

export function fakeD1() {
  const db = new DatabaseSync(":memory:");
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(readFileSync(MIGRATION, "utf8"));
  return {
    raw: db,
    prepare: (sql) => new Stmt(db, sql),
    // D1 的 batch 是交易：任一句失敗就全部回滾
    async batch(stmts) {
      db.exec("BEGIN");
      try {
        const out = stmts.map((s) => s.exec());
        db.exec("COMMIT");
        return out;
      } catch (e) {
        db.exec("ROLLBACK");
        throw e;
      }
    },
  };
}

export const brokenD1 = () => ({
  prepare() {
    throw new Error("D1 down");
  },
  async batch() {
    throw new Error("D1 down");
  },
});
