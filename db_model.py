import sqlite3
from typing import List, Dict, Any, Optional
from text_parser import parse_financial_notes
from category_engine import CategorizationEngine
from pathlib import Path

class FinanceModel:
    """
    init_db() -> Instantiates tables if doesnt exist yet
    
    SETUP AND SEEDERS
    add_category(name: str, cat_type: str) -> inserts new cat, returns id
    add_account(name: str) -> inserts new acc, returns id
    
    ADDERS
    add_transaction(date: str, amount: float, description: str, ategory_id: int, account_id: int) -> inserts transac event into db
    add_keyword_rule(keyword: str, category_id: int, apply_retroactively: bool = True) -> adds keyword rule for future categorization 
    
    GETTERS
    get_account_id(name: str) -> retrieves acc id, if doesnt exist, creates it and returns acc id
    get_category_for_description(raw_description: str, amount: float) -> returns category id given description
    get_daily_summary(target_date: str) -> retrieves data for specific date
    get_all_transactions_view() -> retrieves data across entire db, ordered chronologically

    STATUS / FILTERS
    get_account_balances() -> net balance per account
    get_category_totals() -> total amount per category
    get_transactions_by_account(account_name: str) -> transactions for one account, chronologically
    get_transactions_by_category(category_name: str) -> transactions for one category, chronologically
    
    """
    # Dates are stored exactly as the user typed them - e.g. "7/8", "7/20" -
    # with no year and no zero-padding. Plain `ORDER BY date` sorts those as
    # text, so "7/20" sorts before "7/8" (the character '2' < '8'). This
    # expression splits each date on '/' and casts month/day to INTEGER so
    # they sort numerically (i.e. chronologically within a year) instead.
    # It assumes the "M/D" format text_parser currently produces.
    _CHRONOLOGICAL_ORDER = """
        CAST(substr(t.date, 1, instr(t.date, '/') - 1) AS INTEGER) ASC,
        CAST(substr(t.date, instr(t.date, '/') + 1) AS INTEGER) ASC,
        t.id ASC
    """

    def __init__(self, db_path: str = "finance.db"):
        """Initializes the connection and ensures tables exist."""
        self.db_path = db_path
        self._category_engine = CategorizationEngine(db_path)
        
    def _get_connection(self) -> sqlite3.Connection:
        """Creates a connection that returns rows as dictionary-like objects."""
        conn = sqlite3.connect(self.db_path)
        # Enables Foreign Key enforcement (disabled by default in SQLite)
        conn.execute("PRAGMA foreign_keys = ON;")
        # Allows accessing columns by name: row['amount'] instead of row[2]
        conn.row_factory = sqlite3.Row 
        return conn
    
    def init_db(self):
        """Creates the normalized schema if it doesn't already exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Categories Table
            # name uses COLLATE NOCASE so "Needs" and "needs" are the same
            # category everywhere: the UNIQUE constraint rejects case-only
            # duplicates on insert, and every `WHERE name = ?` lookup below
            # matches regardless of case, instead of silently creating a
            # second category that splits totals/keyword rules across two ids.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    type TEXT NOT NULL CHECK(type IN ('Income', 'Expense'))
                );
            """)
            
            # 2. Accounts Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                );
            """)
            
            # 3. Keywords Table            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT UNIQUE NOT NULL,
                    category_id INTEGER NOT NULL,
                    FOREIGN KEY (category_id) REFERENCES categories (id)
                );
            """)
            
            # 4. Transactions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT NOT NULL,
                    category_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    FOREIGN KEY (category_id) REFERENCES categories (id),
                    FOREIGN KEY (account_id) REFERENCES accounts (id)
                );
            """)

            # 5. Guarantee the two fallback buckets always exist. Categorization's
            # TIER 3 fallback depends on "Uncategorized Income" / "Uncategorized
            # Expense" being present - if a user's own category list never
            # includes them, the fallback used to silently drop the transaction
            # into hardcoded category id 1, regardless of whether that category's
            # type actually matched the transaction's sign. Seeding both here,
            # every time init_db() runs, closes that gap.
            cursor.execute("INSERT OR IGNORE INTO categories (name, type) VALUES ('Uncategorized Expense', 'Expense');")
            cursor.execute("INSERT OR IGNORE INTO categories (name, type) VALUES ('Uncategorized Income', 'Income');")

            conn.commit()
            
    # --- SETUP / SEED METHODS ---

    def add_category(self, name: str, cat_type: str) -> Optional[int]:
        """Inserts a new category and returns its ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO categories (name, type) VALUES (?, ?);", 
                    (name, cat_type)
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Category already exists
            return self.get_category_id(name)

    def add_account(self, name: str) -> Optional[int]:
        """Inserts a new account and returns its ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO accounts (name) VALUES (?);", (name,))
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            return self.get_account_id(name)
        
    # --- TRANSACTION (CRUD) METHODS ---

    def add_transaction(self, date: str, amount: float, description: str, category_id: int, account_id: int) -> int:
        """Inserts a single transaction event into the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (date, amount, description, category_id, account_id)
                VALUES (?, ?, ?, ?, ?);
            """, (date, amount, description, category_id, account_id))
            return cursor.lastrowid
        
    def add_keyword_rule(self, keyword: str, category_id: int, apply_retroactively: bool = True):
        """
        Adds a keyword rule for future categorization and optionally 
        retroactively updates any existing transactions that match the keyword.

        The retroactive update only touches transactions whose amount sign
        agrees with the target category's type (Income = positive amount,
        Expense = zero/negative amount). Without this check, a keyword like
        "daddy" mapped to an Income category could reach back and overwrite
        an unrelated Expense transaction that happens to contain the same
        word (e.g. "daddy" as an Expense payee elsewhere) - the exact
        Income/Expense bleed the sign-aware categorization is meant to avoid.
        """
        with self._get_connection() as conn:
            clean_kw = keyword.lower().strip()
            
            # 1. Save the rule for future transactions
            conn.execute("INSERT OR REPLACE INTO keyword_rules (keyword, category_id) VALUES (?, ?);", 
                            (clean_kw, category_id))
            
            # 2. Retroactively update past transactions matching this keyword,
            #    filtered to the ones whose sign matches this category's type.
            if apply_retroactively:
                cursor = conn.execute("SELECT type FROM categories WHERE id = ?;", (category_id,))
                row = cursor.fetchone()
                category_type = row["type"] if row else None

                if category_type == "Income":
                    sign_clause = "amount > 0"
                elif category_type == "Expense":
                    sign_clause = "amount <= 0"
                else:
                    # Unknown/missing category - skip the retroactive update
                    # rather than risk reassigning transactions of the wrong sign.
                    sign_clause = None

                if sign_clause:
                    conn.execute(f"""
                        UPDATE transactions 
                        SET category_id = ? 
                        WHERE LOWER(description) LIKE '%' || ? || '%'
                          AND {sign_clause};
                    """, (category_id, clean_kw))
                
        conn.commit()
        
    def get_account_id(self, name: str) -> int:
        """
        Retrieves the ID for a given account name. 
        If the account doesn't exist yet, it automatically creates it 
        to prevent foreign key insertion errors.
        """
        with self._get_connection() as conn:
            clean_name = name.strip()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM accounts WHERE name = ? LIMIT 1;", (clean_name,))
            row = cursor.fetchone()
            
            if row:
                return row["id"]
            else:
                # Fallback: create the account on the fly if it wasn't found
                return self.add_account(clean_name)
        
    def get_category_id(self, name: str, default_type: str = "Expense") -> int:
        """
        Retrieves the ID for a given category name. 
        If the category doesn't exist yet, it automatically creates it 
        to prevent foreign key insertion errors.
        """
        with self._get_connection() as conn:
            clean_name = name.strip()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM categories WHERE name = ? COLLATE NOCASE LIMIT 1;", (clean_name,))
            row = cursor.fetchone()
            
            if row:
                return row["id"]
            else:
                # Fallback: create the category on the fly using the default type
                return self.add_category(clean_name, default_type)
    
    def get_category_for_description(self, raw_description: str, amount: float) -> int:
        """
        Determines the category_id using the description AND the math sign
        to separate Income from Expense categories.

        Delegates to CategorizationEngine (category_engine.py) so this logic
        lives in exactly one place instead of being duplicated here and there.
        """
        return self._category_engine.get_category_for_description(raw_description, amount)

    def get_daily_summary(self, target_date: str) -> List[Dict[str, Any]]:
        """
        Recreates your spreadsheet grid dynamically by joining tables
        for a specific date.
        """
        query = """
            SELECT 
                t.id,
                t.date,
                t.amount,
                t.description,
                c.name as category,
                c.type as type,
                a.name as account
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            JOIN accounts a ON t.account_id = a.id
            WHERE t.date = ?
            ORDER BY t.id DESC;
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (target_date,))
            rows = cursor.fetchall()
            # Convert sqlite3.Row objects to standard Python dictionaries
            return [dict(row) for row in rows]
        
    def get_all_transactions_view(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT t.date, t.amount, t.description, c.name as category, c.type as type, a.name as account
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                JOIN accounts a ON t.account_id = a.id
                ORDER BY {self._CHRONOLOGICAL_ORDER};
            """)
            return [dict(row) for row in cursor.fetchall()]

    # --- STATUS / FILTER METHODS ---

    def get_account_balances(self) -> List[Dict[str, Any]]:
        """
        Net balance (sum of all transaction amounts) per account, ordered by
        account name. Expense amounts are stored negative and Income amounts
        positive, so a plain SUM already gives the correct running balance.
        Accounts with zero transactions still show up, with a balance of 0.
        """
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
        """
        Total amount transacted per category, ordered by type then name.
        Totals stay signed (Expense categories will show as negative, Income
        as positive) to match how amounts are stored everywhere else.
        Categories with zero transactions still show up, with a total of 0.
        """
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

    def get_transactions_by_account(self, account_name: str) -> List[Dict[str, Any]]:
        """Filters the full transaction view down to a single account, chronologically."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT t.date, t.amount, t.description, c.name as category, c.type as type, a.name as account
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                JOIN accounts a ON t.account_id = a.id
                WHERE a.name = ?
                ORDER BY {self._CHRONOLOGICAL_ORDER};
            """, (account_name,))
            return [dict(row) for row in cursor.fetchall()]

    def get_transactions_by_category(self, category_name: str) -> List[Dict[str, Any]]:
        """Filters the full transaction view down to a single category, chronologically."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT t.date, t.amount, t.description, c.name as category, c.type as type, a.name as account
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                JOIN accounts a ON t.account_id = a.id
                WHERE c.name = ? COLLATE NOCASE
                ORDER BY {self._CHRONOLOGICAL_ORDER};
            """, (category_name,))
            return [dict(row) for row in cursor.fetchall()]
        
if __name__ == "__main__":
    print("--- 1. INITIALIZING DATABASE & SEEDING RULES ---")
    
    db = FinanceModel("test.db")
    db.init_db()
    # Setup core accounts
    gcash_id = db.add_account("GCash + Cash")

    # Setup categories
    needs_id = db.add_category("Needs", "Expense")
    wants_id = db.add_category("Wants", "Expense")
    uncat_exp_id = db.add_category("Uncategorized Expense", "Expense")
    
    allowance_id = db.add_category("Allowance", "Income")
    uncat_inc_id = db.add_category("Uncategorized Income", "Income")
    
    # Seed explicit keyword rules
    db.add_keyword_rule("gas", needs_id)
    db.add_keyword_rule("romand", wants_id)
    db.add_keyword_rule("daddy", allowance_id) # Traffic cop will ensure this only hits if amount is positive!
    
    print("Database ready. Rules loaded: 'gas'->Needs, 'romand'->Wants, 'daddy'->Allowance\n")
    
    # Sample raw text mirroring your shorthand notes
    sample_notes = """
    7/8 - -264 gas @mari, -113.16 pandecoco @cash, +500 daddy bike @maya
    7/11 - +500 daddy bike @maya
    7/20 - -320 plate number shiz, +500 daddy bike
    """
    
    print("--- 2. PARSING RAW TEXT ---")
    parsed_items = parse_financial_notes(sample_notes)
    for item in parsed_items:
        print(f"Extracted: {item['date']} | {item['amount']} | '{item['description']}'")
    print()
    
    print("--- 3. RUNNING CATEGORIZATION ENGINE & SAVING ---")
    for item in parsed_items:
        # Ask the engine to figure out the category using the description AND math sign
        cat_id = db.get_category_for_description(item["description"], item["amount"])
        
        # Save to database
        db.add_transaction(
            date=item["date"],
            amount=item["amount"],
            description=item["description"],
            category_id=cat_id,
            account_id=gcash_id
        )
        print(f"Routed '{item['description']}' ({item['amount']}) ---> Category ID: {cat_id}")
    print()
    
    print("--- 4. FINAL VIEW: GENERATING SPREADSHEET-STYLE DASHBOARD ---")
    results = db.get_all_transactions_view()
    
    # Format a clean table output
    print(f"{'DATE':<6} | {'AMOUNT':<10} | {'TYPE':<8} | {'CATEGORY':<22} | {'DESCRIPTION'}")
    print("-" * 75)
    for row in results:
        print(f"{row['date']:<6} | {row['amount']:<10.2f} | {row['type']:<8} | {row['category']:<22} | {row['description']}")
        
    print("--- 5. ASSIGNING NEW CATEGORIES TO UNCAT EXPENSES ---")
    
    db.add_keyword_rule('pandecoco', wants_id)
    db.add_keyword_rule('juce', wants_id)
    
    results = db.get_all_transactions_view()
        
    # Format a clean table output
    print(f"{'DATE':<6} | {'AMOUNT':<10} | {'TYPE':<8} | {'CATEGORY':<22} | {'DESCRIPTION'}")
    print("-" * 75)
    for row in results:
        print(f"{row['date']:<6} | {row['amount']:<10.2f} | {row['type']:<8} | {row['category']:<22} | {row['description']}")