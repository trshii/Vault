"""
db_model.py
-----------
Model layer (MVC). Owns the SQLite connection, schema, and all reads/writes.

This is a deliberately "dumb" data layer now: there is no categorization
logic living here anymore (CategorizationEngine / keyword_rules are gone).
The Model only ever does one of two things with a tag name:
  1. look it up and return the existing id, or
  2. create it fresh, using a type the CALLER supplies.
All "what category does this belong to" decisions happen in the parser
(explicit #tag) or the Controller (Uncategorized fallback) — never here.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List


class FinanceModel:
    """
    init_db()                                  -> creates the 3-table schema if missing
    get_account_id(name)                       -> get-or-create an account, returns id
    get_or_create_category(name, inferred_type)-> get-or-create a category, returns id
    get_uncategorized_bucket_id(tx_type)       -> id of the Uncategorized Inflow/Outflow bucket
    add_transaction(...)                       -> inserts one transaction row
    get_all_transactions_view()                -> full transaction list, chronological
    get_account_balances()                     -> net balance per account
    get_category_totals()                      -> total amount per category
    """

    # Dates are stored exactly as typed (e.g. "8/4", "12/1") — no year, no
    # zero-padding. Plain `ORDER BY date` would sort those as text
    # ("12/1" before "8/4"), so this splits on '/' and casts month/day to
    # INTEGER for a real chronological sort within a year.
    _CHRONOLOGICAL_ORDER = """
        CAST(substr(t.date, 1, instr(t.date, '/') - 1) AS INTEGER) ASC,
        CAST(substr(t.date, instr(t.date, '/') + 1) AS INTEGER) ASC,
        t.id ASC
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row  # access columns by name: row["amount"]
        return conn

    def init_db(self) -> None:
        """Creates the lean schema (mirrors schema.sql) if it doesn't exist yet."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    type TEXT NOT NULL CHECK (type IN ('inflow', 'outflow'))
                );
            """)

            cursor.execute("""
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
            """)

            # Guarantee both fallback buckets exist so an untagged
            # transaction always has somewhere deterministic to land.
            cursor.execute(
                "INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?);",
                ("Uncategorized Inflow", "inflow"),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?);",
                ("Uncategorized Outflow", "outflow"),
            )
            conn.commit()

    # --- GET-OR-CREATE RESOLVERS --------------------------------------------
    # These turn an explicit tag string from the parser into a database id.
    # This is materialization, not categorization — the name is already
    # decided; we're just making sure a row exists for it.

    def get_account_id(self, name: str) -> int:
        clean_name = name.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM accounts WHERE name = ? COLLATE NOCASE LIMIT 1;",
                (clean_name,),
            )
            row = cursor.fetchone()
            if row:
                return row["id"]

            cursor.execute("INSERT INTO accounts (name) VALUES (?);", (clean_name,))
            conn.commit()
            return cursor.lastrowid

    def get_or_create_category(self, name: str, inferred_type: str) -> int:
        """
        inferred_type must be 'inflow' or 'outflow'. It's only used if the
        category doesn't exist yet and has to be created — an existing
        category keeps whatever type it already has.
        """
        if inferred_type not in ("inflow", "outflow"):
            raise ValueError(
                f"inferred_type must be 'inflow' or 'outflow', got {inferred_type!r}"
            )

        clean_name = name.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE LIMIT 1;",
                (clean_name,),
            )
            row = cursor.fetchone()
            if row:
                return row["id"]

            cursor.execute(
                "INSERT INTO categories (name, type) VALUES (?, ?);",
                (clean_name, inferred_type),
            )
            conn.commit()
            return cursor.lastrowid

    def get_uncategorized_bucket_id(self, tx_type: str) -> int:
        """tx_type is 'inflow' or 'outflow'."""
        bucket_name = (
            "Uncategorized Inflow" if tx_type == "inflow" else "Uncategorized Outflow"
        )
        return self.get_or_create_category(bucket_name, tx_type)

    # --- WRITE ---------------------------------------------------------------

    def add_transaction(
        self,
        date: str,
        amount: float,
        description: str,
        account_id: int,
        category_id: int,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions (date, amount, description, account_id, category_id)
                VALUES (?, ?, ?, ?, ?);
                """,
                (date, amount, description, account_id, category_id),
            )
            conn.commit()
            return cursor.lastrowid

    # --- READ (feeds VaultMarkdownView) ---------------------------------------

    def get_all_transactions_view(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT t.date, t.amount, t.description,
                       c.name AS category, c.type AS type, a.name AS account
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                JOIN accounts a   ON t.account_id  = a.id
                ORDER BY {self._CHRONOLOGICAL_ORDER};
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_account_balances(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.name AS account, COALESCE(SUM(t.amount), 0) AS balance
                FROM accounts a
                LEFT JOIN transactions t ON t.account_id = a.id
                GROUP BY a.id
                ORDER BY a.name COLLATE NOCASE ASC;
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_category_totals(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.name AS category, c.type AS type, COALESCE(SUM(t.amount), 0) AS total
                FROM categories c
                LEFT JOIN transactions t ON t.category_id = c.id
                GROUP BY c.id
                ORDER BY c.type ASC, c.name COLLATE NOCASE ASC;
            """)
            return [dict(row) for row in cursor.fetchall()]
