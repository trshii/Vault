import sqlite3
import os
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

    # Dates are stored as zero-padded ISO strings ('YYYY-MM-DD'), so a plain
    # lexicographic sort is already chronologically correct — no manual
    # date-part parsing needed, and it sorts correctly across year boundaries.
    _CHRONOLOGICAL_ORDER = "t.date ASC, t.id ASC"

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
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
                    source_file TEXT NOT NULL, 
                    FOREIGN KEY (account_id)  REFERENCES accounts (id),
                    FOREIGN KEY (category_id) REFERENCES categories (id)
                );
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scanned_files (
                    filepath TEXT PRIMARY KEY,
                    last_modified REAL
                );
            """)

            cursor.execute(
                "INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?);",
                ("Uncategorized Inflow", "inflow"),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?);",
                ("Uncategorized Outflow", "outflow"),
            )
            conn.commit()

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
        source_file: str, # NEW PARAMETER
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO transactions (date, amount, description, account_id, category_id, source_file)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (date, amount, description, account_id, category_id, source_file),
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
        
    def needs_processing(self, filepath: str, current_mtime: float) -> bool:
        """Queries SQLite to see if the file is new or has been modified."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_modified FROM scanned_files WHERE filepath = ?", 
                (filepath,)
            )
            row = cursor.fetchone()
            
            if row is None or current_mtime > row["last_modified"]:
                return True
            return False

    def mark_as_processed(self, filepath: str, current_mtime: float) -> None:
        """Upserts the file tracking data into SQLite."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scanned_files (filepath, last_modified) 
                VALUES (?, ?)
                ON CONFLICT(filepath) DO UPDATE SET last_modified = excluded.last_modified
            """, (filepath, current_mtime))
            conn.commit()

    def get_recently_processed_files(self, limit: int = 5) -> List[str]:
        """Retrieves the most recently modified files from the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filepath FROM scanned_files 
                ORDER BY last_modified DESC LIMIT ?
            """, (limit,))
            return [row["filepath"] for row in cursor.fetchall()]
        
    def delete_transactions_by_file(self, filepath: str) -> None:
            """Wipes all existing transactions from a specific file before re-parsing."""
            with self._get_connection() as conn:
                conn.execute("DELETE FROM transactions WHERE source_file = ?", (filepath,))
                conn.commit()
