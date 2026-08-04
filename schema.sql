-- ============================================================
-- Vault: Personal Finance Tracker — SQLite Schema
-- ============================================================
-- Refactor notes:
--   * keyword_rules is REMOVED entirely. Categorization is no longer
--     inferred/guessed anywhere in the system — the parser requires an
--     explicit #category tag, or the transaction falls back to one of
--     the two seeded "Uncategorized" buckets below.
--   * categories.type now uses 'inflow' / 'outflow' (matches the sign
--     of the amount) instead of the old 'Income' / 'Expense'.
--   * This file is mirrored by FinanceModel.init_db() in db_model.py,
--     which is what actually runs at startup. Keep the two in sync if
--     you edit one — this file exists so you can also inspect/apply
--     the schema directly with the sqlite3 CLI if you ever want to.
-- ============================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
    type TEXT NOT NULL CHECK (type IN ('inflow', 'outflow'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    amount      REAL NOT NULL,
    description TEXT NOT NULL,
    account_id  INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    FOREIGN KEY (account_id)  REFERENCES accounts (id),
    FOREIGN KEY (category_id) REFERENCES categories (id)
);

-- Two fallback buckets so a transaction with no #category tag is never
-- dropped or misfiled. Re-run safely every startup via INSERT OR IGNORE.
INSERT OR IGNORE INTO categories (name, type) VALUES ('Uncategorized Inflow',  'inflow');
INSERT OR IGNORE INTO categories (name, type) VALUES ('Uncategorized Outflow', 'outflow');
