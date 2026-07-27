import sqlite3
from typing import Optional

class CategorizationEngine:
    def __init__(self, db_path: str = "finance.db"):
        self.db_path = db_path

    def get_category_for_description(self, raw_description: str, amount: float) -> int:
        """
        Determines the category_id using the description AND the math sign
        to separate Income from Expense categories.
        """
        clean_desc = raw_description.lower().strip()
        
        # 1. Determine the required category type based on the math sign
        required_type = "Income" if amount > 0 else "Expense"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # --- TIER 1: Explicit Keyword Rules (Filtered by Type) ---
            # We JOIN the categories table to ensure we only match rules 
            # that match the 'Income' or 'Expense' requirement.
            cursor.execute("""
                SELECT r.category_id 
                FROM keyword_rules r
                JOIN categories c ON r.category_id = c.id
                WHERE ? LIKE '%' || r.keyword || '%'
                  AND c.type = ?
                LIMIT 1;
            """, (clean_desc, required_type))
            
            row = cursor.fetchone()
            if row:
                return row[0]

            # --- TIER 2: Historical Lookup (Filtered by Type) ---
            # Even if you bought a "bike" as an Expense last month, 
            # if today's entry is "+500 bike", it will ignore the Expense history
            # and only look for Income history!
            cursor.execute("""
                SELECT t.category_id 
                FROM transactions t
                JOIN categories c ON t.category_id = c.id
                WHERE LOWER(t.description) = ? 
                  AND c.type = ?
                ORDER BY t.id DESC 
                LIMIT 1;
            """, (clean_desc, required_type))
            
            row = cursor.fetchone()
            if row:
                return row[0]

            # --- TIER 3: Fallback to the correct Uncategorized bucket ---
            # FinanceModel.init_db() guarantees 'Uncategorized Income' and
            # 'Uncategorized Expense' both exist, so this should always find a
            # row. If it doesn't, something upstream skipped init_db() - better
            # to raise than to silently drop the transaction into an arbitrary
            # hardcoded category (which previously caused Income transactions
            # to get miscategorized into whatever category happened to have id 1).
            fallback_name = f"Uncategorized {required_type}"
            cursor.execute("SELECT id FROM categories WHERE name = ? LIMIT 1;", (fallback_name,))
            row = cursor.fetchone()
            
            if row:
                return row[0]
            raise RuntimeError(
                f"Fallback category '{fallback_name}' not found. "
                "Make sure FinanceModel.init_db() has been called."
            )