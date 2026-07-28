import json
from pathlib import Path
from typing import *
from db_model import FinanceModel
from text_parser import parse_financial_notes
from vault_view_tmnl import VaultTmnlView


class VaultController:
    def __init__(self, model: FinanceModel, view: VaultTmnlView) -> None:
        self._db_model = model
        self._view = view
        self.ROOT = Path(__file__).resolve().parent
        self.CONFIG_PATH = self.ROOT / "config" / "config.json"
        self._db_model.init_db()
        
    @property
    def has_first_init(self) -> bool:
        app_state = self.get_app_state()
        return app_state['has_first_init']
    
    def get_user_acc(self) -> None:
        accounts: List[str] = self._view.get_user_accounts()
        for account in accounts:
            self._db_model.add_account(account)
            
    def get_user_cat(self) -> None:
        categories: Dict[str, List[str]] = self._view.get_user_categories()
        for cat_type, category_list in categories.items():
            for category in category_list:
                self._db_model.add_category(category, cat_type)
    
    def init_acc_cat_setup(self) -> None:
        self.get_user_acc()
        self.get_user_cat()
                
    def get_input_and_parse(self) -> List[Dict[str, Any]]:
        user_list = self._view.get_user_list()
        user_list_parsed: List[Dict[str, Any]] = parse_financial_notes(user_list)
        return user_list_parsed
                
    def get_new_transaction(self, default_account: Optional[str] = None) -> None:
        parsed_data = self.get_input_and_parse()
        for item in parsed_data:
            self.process_data(item, default_account=default_account)
            
    def get_app_state(self) -> dict[str, Any]:
        if not self.CONFIG_PATH.exists():
            return {}
        else:
            with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
            
    def set_keyword_rule(self) -> None:
        """
        Prompts for a keyword and the category it should map to, resolves
        that category case-insensitively (creating it as `cat_type` only if
        it doesn't already exist - see FinanceModel.get_category_id), and
        saves the rule. If the user opts in, existing transactions that
        already match the keyword and share the category's sign are
        reclassified too (see FinanceModel.add_keyword_rule).
        """
        keyword, category_name, cat_type, apply_retroactively = self._view.prompt_keyword_rule()

        if not keyword or not category_name:
            print("Keyword and category are both required - nothing was saved.\n")
            return

        category_id = self._db_model.get_category_id(category_name, default_type=cat_type)
        self._db_model.add_keyword_rule(keyword, category_id, apply_retroactively=apply_retroactively)
        print(f"Keyword rule saved: '{keyword}' -> '{category_name}'.\n")
            
    def write_app_state(self, data: Dict[str, Any]) -> None:
        """Writes a Python dictionary to the config JSON file safely."""
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            
            # Step 3: Dump the dictionary to the file with clean indentation
            json.dump(data, f, indent=4)
                
    
    def process_data(self, item: Dict[str, Any], default_account: Optional[str] = None) -> None:
        """
        Resolves the account and category for a single parsed item and
        saves it as a transaction.

        Account: each item can carry its own account name, tagged inline in
        the notes as "@account" and picked up by text_parser. If an item has
        no tag, default_account is used instead. Raises if neither is
        available, since every transaction needs an account_id to satisfy
        the accounts foreign key.

        Category: if the item carries an inline "#category" tag, that
        category is resolved case-insensitively (created fresh - with its
        Income/Expense type inferred from this transaction's sign - if it
        doesn't exist yet), and is also saved as a keyword rule keyed on
        this transaction's own description. That means tagging one line
        also retroactively re-categorizes every other transaction already
        in the db with a matching description/sign, and future ones too via
        CategorizationEngine's Tier 1 - handy for auto-categorizing a whole
        first-time list without pre-declaring categories or writing keyword
        rules by hand. Items with no "#category" tag fall back to the
        normal keyword/history/uncategorized lookup, unchanged.
        """
        account_name = item.get("account") or default_account
        if account_name is None:
            raise ValueError(
                f"No account found for transaction {item['description']!r} "
                f"and no default_account was provided."
            )

        acc_id = self._db_model.get_account_id(account_name)

        category_tag = item.get("category")
        if category_tag:
            inferred_type = "Income" if item["amount"] > 0 else "Expense"
            cat_id = self._db_model.get_category_id(category_tag, default_type=inferred_type)
            self._db_model.add_keyword_rule(item["description"], cat_id, apply_retroactively=True)
        else:
            cat_id = self._db_model.get_category_for_description(item["description"], item["amount"])

        # Save to database
        self._db_model.add_transaction(
            date=item["date"],
            amount=item["amount"],
            description=item["description"],
            category_id=cat_id,
            account_id=acc_id
        )
    
    def show_account_balances(self) -> None:
        balances = self._db_model.get_account_balances()
        self._view.display_account_balances(balances)

    def show_category_totals(self) -> None:
        totals = self._db_model.get_category_totals()
        self._view.display_category_totals(totals)

    def filter_by_account(self) -> None:
        account_name = self._view.prompt_account_filter()
        results = self._db_model.get_transactions_by_account(account_name)
        self._view.display_dashboard(results)

    def filter_by_category(self) -> None:
        category_name = self._view.prompt_category_filter()
        results = self._db_model.get_transactions_by_category(category_name)
        self._view.display_dashboard(results)

    def init_run(self, default_account: Optional[str] = None) -> None:
        """
        First-time setup. Asks for the transaction list up front instead of
        making the user separately enumerate accounts and categories first:
        - accounts referenced via "@account" tags are created automatically
          (FinanceModel.get_account_id already does this on the fly).
        - categories referenced via "#category" tags are created and
          auto-applied too, including retroactively across the rest of this
          same list (see process_data).
        Only after that do we ask for any additional accounts that didn't
        happen to show up in the list yet (e.g. a savings account with no
        transactions so far). Categories aren't prompted for here anymore -
        `get_user_cat` (menu option "I") is still available any time for
        pre-declaring categories that aren't tagged inline.
        """
        self._view.clear()
        self.get_new_transaction(default_account=default_account)
        self.get_user_acc()
        config = {"has_first_init": True}
        self.write_app_state(config)
        self.run(default_account=default_account)
                    
    def run(self, default_account: Optional[str] = None) -> None:
        self._view.clear()
        while True:
            input_cmd = self._view.get_optional_input().strip().lower()
            match input_cmd:
                case "d":
                    results = self._db_model.get_all_transactions_view()
                    self._view.display_dashboard(results)
                case "a":
                    self.get_new_transaction(default_account=default_account)
                case "b":
                    self.show_account_balances()
                case "c":
                    self.show_category_totals()
                case "f":
                    self.filter_by_account()
                case "g":
                    self.filter_by_category()
                case "h":
                    self.get_user_acc()
                case "i":
                    self.get_user_cat()
                case "k":
                    self.set_keyword_rule()
                case "q":
                    break
                case _:
                    print(f"Unrecognized command: {input_cmd!r}\n")
        
            
    