"""
vault_controller.py
--------------------
Controller layer (MVC). Wires parser output to the model.

The old interactive terminal loop (run/init_run, menu commands, etc.) is
gone. `process_batch` is now the single entry point — the CLI calls it
once per invocation with the whole payload, and it's responsible for:
  1. parsing every line (via text_parser.parse_batch),
  2. resolving each parsed line's @account / #category tags to db ids
     (creating them on first sight, but never guessing them), and
  3. inserting a transaction row for every line that parsed successfully.

A line that fails to parse is skipped, not fatal — see BatchResult.
"""

from dataclasses import dataclass, field
from typing import List

from db_model import FinanceModel
from text_parser import ParsedTransaction, ParserError, parse_batch


@dataclass
class BatchResult:
    inserted: List[ParsedTransaction] = field(default_factory=list)
    errors: List[ParserError] = field(default_factory=list)

    @property
    def had_errors(self) -> bool:
        return len(self.errors) > 0


class VaultController:
    def __init__(self, model: FinanceModel) -> None:
        self._db_model = model
        self._db_model.init_db()

    def process_batch(self, raw_text: str) -> BatchResult:
        """
        Parses every line of `raw_text` and inserts whatever parses
        cleanly. Lines that fail to parse (bad format, missing @account)
        are collected as errors and do NOT stop the rest of the batch.
        """
        parsed_items, parse_errors = parse_batch(raw_text)

        result = BatchResult(errors=list(parse_errors))

        for item in parsed_items:
            self._insert_transaction(item)
            result.inserted.append(item)

        return result

    def _insert_transaction(self, item: ParsedTransaction) -> None:
        account_id = self._db_model.get_account_id(item.account)

        tx_type = "inflow" if item.amount > 0 else "outflow"
        if item.category:
            # Explicit #tag from the parser — materialize it, inferring
            # type from this transaction's sign only if it's brand new.
            category_id = self._db_model.get_or_create_category(item.category, tx_type)
        else:
            # No tag at all: strict Uncategorized bucket, never a guess.
            category_id = self._db_model.get_uncategorized_bucket_id(tx_type)

        self._db_model.add_transaction(
            date=item.date,
            amount=item.amount,
            description=item.description,
            account_id=account_id,
            category_id=category_id,
        )
