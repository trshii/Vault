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
        
    def clear(self) -> None:
        if os.name == "nt":
        # Windows requires shell=True to run internal commands like 'cls'
            subprocess.run("cls", shell=True)
        else:
            # macOS/Linux can call 'clear' directly as an executable list
            subprocess.run(["clear"])
        
    def get_user_list(self) -> str:
        self.clear()
        print("Please input list (press ENTER on blank line to finish.) ")
        print("FORMAT: 'M/D - (-/+) description @account, (-/+) description @account'")
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
        user_categories = {"Expenses": [], "Income": []}
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
            
        user_categories['Expenses'] = expenses
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

    def get_optional_input(self) -> str:
        option = input("""
                       Commands:
                       D: Display Dashboard
                       A: Add Transaction List
                       B: Show Account Balances
                       C: Show Category Totals
                       F: Filter Transactions by Account
                       G: Filter Transactions by Category
                       H: Add Accounts
                       I: Add Categories
                       Q: Quit
                       """)
        
        return option