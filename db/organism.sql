-- LIFE v2.2 organism database: /home/operator/.local/state/life/organism.sqlite3
-- The database the organism grows itself. It starts with only the migration ledger below. Every later
-- table arrives as an additive migration drafted by a database cell and applied by bin/life-tick.py after
-- code validation (LIFE.md section 7.8; the exact grammar is life_common.MIGRATION_RULES): only CREATE TABLE IF NOT
-- EXISTS, CREATE [UNIQUE] INDEX IF NOT EXISTS and ALTER TABLE ... ADD COLUMN, every name starts with org_, no
-- AUTOINCREMENT, no quoted identifier. Nothing is ever dropped or deleted. Rows arrive only through the store adapter
-- (quote-verified knowledge into org_ tables whose columns are fact_id plus source_url, claim, quote, created_at) or the
-- operator. The control registry (life.sqlite3) is a separate file, so a migration can never touch control state.

CREATE TABLE IF NOT EXISTS schema_migrations (
  migration_id TEXT NOT NULL PRIMARY KEY CHECK (length(migration_id) BETWEEN 6 AND 45),
  sha256       TEXT NOT NULL CHECK (length(sha256) = 64),
  applied_at   INTEGER NOT NULL
);
