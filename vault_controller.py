from typing import *
from db_model import FinanceModel
from text_parser import parse_financial_notes
from vault_view_tmnl import VaultTmnlView


class VaultController:
    def __init__(self, model: FinanceModel, view: VaultTmnlView) -> None:
        self._db_model = model
        self._view = view
        
        self._db_model.init_db()
        
    def get_input_and_parse(self) -> List[Dict[str, Any]]:
        user_list = self._view.get_user_list()
        user_list_parsed: List[Dict[str, Any]] = parse_financial_notes(user_list)
        return user_list_parsed
    
    def init_acc_cat_setup(self) -> None:
        accounts: List[str] = self._view.get_user_accounts()
        categories: Dict[str, List[str]] = self._view.get_user_categories()
        
        for account in accounts:
            self._db_model.add_account(account)
            
        for cat_type, category_list in categories.items():
            for category in category_list:
                self._db_model.add_category(category, cat_type)
                
    def get_new_transaction(self, default_account: Optional[str] = None) -> None:
        parsed_data = self.get_input_and_parse()
        for item in parsed_data:
            self.process_data(item, default_account=default_account)
                
    
    def process_data(self, item: Dict[str, Any], default_account: Optional[str] = None) -> None:
        """
        Resolves the account for a single parsed item and saves it as a
        transaction. Each item can carry its own account name, tagged
        inline in the notes as "@account" and picked up by text_parser.
        If an item has no tag, default_account is used instead. Raises if
        neither is available, since every transaction needs an account_id
        to satisfy the accounts foreign key.
        """
        account_name = item.get("account") or default_account
        if account_name is None:
            raise ValueError(
                f"No account found for transaction {item['description']!r} "
                f"and no default_account was provided."
            )

        acc_id = self._db_model.get_account_id(account_name)
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
        self.init_acc_cat_setup()
        self.get_new_transaction(default_account=default_account)

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
                case "q":
                    break
                case _:
                    print(f"Unrecognized command: {input_cmd!r}\n")
            
    