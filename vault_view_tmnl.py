import os
import subprocess
from db_model import FinanceModel
from text_parser import parse_financial_notes
from typing import *

class VaultTmnlView:
    def display_dashboard(self, results: List[Dict[str, Any]]) -> None:
        self.clear()
        print(f"{'DATE':<6} | {'AMOUNT':<10} | {'TYPE':<8} | {'CATEGORY':<22} | {'DESCRIPTION'}")
        print("-" * 75)
        for row in results:
            print(f"{row['date']:<6} | {row['amount']:<10.2f} | {row['type']:<8} | {row['category']:<22} | {row['description']}")
        print()
        
    def display_header(self) -> None:
        print("---------- Vault ----------")
        print()
        print()
        
    def clear(self) -> None:
        if os.name == "nt":
        # Windows requires shell=True to run internal commands like 'cls'
            subprocess.run("cls", shell=True)
        else:
            # macOS/Linux can call 'clear' directly as an executable list
            subprocess.run(["clear"])
            
        self.display_header()
            
    def get_db_file_name(self) -> str:
        self.clear()
        print("Please input .db file name: ")
        file_name = input()
        
        return file_name + ".db"
        
    def get_user_list(self) -> str:
        self.clear()
        print("Please input list (press ENTER on blank line to finish.) ")
        print("FORMAT: 'Month/Day - (-/+) description @account #category, (-/+) description @account #category'")
        print("(@account and #category are both optional, and can appear in either order.")
        print(" Accounts are created automatically if new. A #category tag also saves a")
        print(" keyword rule from the description, so matching transactions - past and")
        print(" future - get auto-categorized too.)")
        lines = []
        
        while True:
            line = input()
            if line == "":
                break
            
            lines.append(line)
            
        user_list = "\n".join(lines)
        
        return user_list
    
    def get_user_accounts(self) -> List[str]:
        self.clear()
        print("Enumerate account delegation (press ENTER on blank line to finish.): ")
        lines = []
                
        while True:
            line = input()
            if line == "":
                break
            
            lines.append(line)
        
        return lines
    
    def get_user_categories(self) -> Dict[str, List[str]]:
        self.clear()
        user_categories = {"Expense": [], "Income": []}
        expenses = []
        income = []
        
        # Expenses
        print("Enter EXPENSES categories (press ENTER on blank line to finish.): ")
        while True:
            line = input()
            if line == "":
                break
            
            expenses.append(line)
            
        # Income
        print("Enter INCOME categories (press ENTER on blank line to finish.): ")
        while True:
            line = input()
            if line == "":
                break
            
            income.append(line)
            
        user_categories['Expense'] = expenses
        user_categories['Income'] = income
        
        return user_categories
    
    def display_account_balances(self, balances: List[Dict[str, Any]]) -> None:
        self.clear()
        print(f"{'ACCOUNT':<20} | {'BALANCE':>12}")
        print("-" * 35)
        for row in balances:
            print(f"{row['account']:<20} | {row['balance']:>12.2f}")
        print()

    def display_category_totals(self, totals: List[Dict[str, Any]]) -> None:
        self.clear()
        print(f"{'CATEGORY':<20} | {'TYPE':<8} | {'TOTAL':>12}")
        print("-" * 45)
        for row in totals:
            print(f"{row['category']:<20} | {row['type']:<8} | {row['total']:>12.2f}")
        print()

    def prompt_account_filter(self) -> str:
        self.clear()
        return input("Enter account name to filter by: ").strip()

    def prompt_category_filter(self) -> str:
        self.clear()
        return input("Enter category name to filter by: ").strip()

    def prompt_keyword_rule(self) -> Tuple[str, str, str, bool]:
        """
        Collects everything needed to set a keyword rule: the keyword itself,
        the category it should route to, a fallback type to use ONLY if that
        category doesn't exist yet (get_category_id needs one to create it),
        and whether to reclassify existing matching transactions.
        """
        self.clear()
        print("Set a keyword rule (auto-categorizes transactions containing this keyword).")
        keyword = input("Keyword to match: ").strip()
        category_name = input("Category to assign it to: ").strip()

        cat_type = input("If that category is new, is it Income or Expense? [Expense]: ").strip().capitalize()
        if cat_type not in ("Income", "Expense"):
            cat_type = "Expense"

        retro_raw = input("Apply retroactively to existing matching transactions? (y/n): ").strip().lower()
        apply_retroactively = retro_raw.startswith("y")

        return keyword, category_name, cat_type, apply_retroactively

    def get_optional_input(self) -> str:
        option = input("""
Commands:
1: Display Dashboard
2: Add Transaction List
3: Show Account Balances
4: Show Category Totals
5: Filter Transactions by Account
W: Filter Transactions by Category
E: Add Accounts
R: Add Categories
T: Set Keyword Rule
A: Change .db File
Q: Quit
- """)
        
        return option