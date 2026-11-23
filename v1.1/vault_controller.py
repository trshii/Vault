import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List
from db_model import FinanceModel
from text_parser import ParsedTransaction, ParserError, parse_batch
from vault_query import QuerySpec, parse_query, summarize


@dataclass
class BatchResult:
    inserted: List[ParsedTransaction] = field(default_factory=list)
    errors: List[ParserError] = field(default_factory=list)

    @property
    def had_errors(self) -> bool:
        return len(self.errors) > 0


@dataclass
class QueryResult:
    spec: QuerySpec
    transactions: List[Dict[str, Any]]
    totals: Dict[str, Any]
    category_totals: List[Dict[str, Any]]
    monthly: List[Dict[str, Any]]
    by_account: List[Dict[str, Any]]


class VaultController:
    def __init__(self, model: FinanceModel, vault_root: Path) -> None:
        self._db_model = model
        self._db_model.init_db()
        self.vault_root_path = vault_root

    def process_batch(self, raw_text: str, source_file: str = "manual_input") -> BatchResult:
        # Isolate the filename from the full path
        filename = Path(source_file).name 
        
        # Safely extract the full date anywhere in the filename
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        
        if match:
            # Keep the year — used to be dropped here, which caused January
            # entries to sort before November ones across a year boundary.
            file_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        else:
            from datetime import datetime
            now = datetime.now()
            file_date = f"{now.year}-{now.month:02d}-{now.day:02d}"

        parsed_items, parse_errors = parse_batch(raw_text, fallback_date=file_date)

        result = BatchResult(errors=list(parse_errors))

        for item in parsed_items:
            self._insert_transaction(item, source_file)
            result.inserted.append(item)

        return result

    def _insert_transaction(self, item: ParsedTransaction, source_file: str) -> None:
        account_id = self._db_model.get_account_id(item.account)

        tx_type = "inflow" if item.amount > 0 else "outflow"
        if item.category:
            category_id = self._db_model.get_or_create_category(item.category, tx_type)
        else:
            category_id = self._db_model.get_uncategorized_bucket_id(tx_type)

        self._db_model.add_transaction(
            date=item.date,
            amount=item.amount,
            description=item.description,
            account_id=account_id,
            category_id=category_id,
            source_file=source_file,
        )
        
    def scan_vault_for_new_transactions(self) -> None:
        """Scans the entire vault for valid daily notes and parses them."""
        for md_file in self.vault_root_path.rglob('*.md'):
            
            if '.vault' in md_file.parts:
                continue
                
            if not re.search(r'\d{4}-\d{2}-\d{2}', md_file.name):
                continue
                
            file_path_str = str(md_file.resolve())
            current_mtime = os.path.getmtime(md_file)
            
            if self._db_model.needs_processing(file_path_str, current_mtime):
                print(f"Reading updated file: {md_file.name}")
                try:
                    content = md_file.read_text(encoding="utf-8")
                    
                    self._db_model.delete_transactions_by_file(file_path_str)
                    
                    self.process_batch(content, source_file=file_path_str)
                    
                    self._db_model.mark_as_processed(file_path_str, current_mtime)
                except Exception as e:
                    print(f"Error reading {md_file.name}: {e}")

    def run_query(self, query_text: str) -> QueryResult:
        """Parses a query string (see vault_query.parse_query) and runs it.
        Raises QueryError on a malformed query."""
        spec = parse_query(query_text)
        rows = self._db_model.query_transactions(
            accounts=spec.accounts,
            categories=spec.categories,
            start=spec.start,
            end=spec.end,
        )
        return QueryResult(spec=spec, transactions=rows, **summarize(rows))
