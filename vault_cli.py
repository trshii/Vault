"""
vault_cli.py
------------
One-shot CLI entrypoint, meant to be invoked by Obsidian's "Shell
Commands" plugin. Replaces the old interactive terminal loop (vault.py /
VaultTmnlView) entirely — every run does exactly one batch of work and
exits.

Usage (single transaction):
    python vault_cli.py \
        --db data/finance.db \
        --dashboard /path/to/vault/Dashboard.md \
        --input "8/4 - 150 gas for giorno+ @wallet #transport"

Usage (multi-line payload — Shell Commands can pass a \\n-joined string):
    python vault_cli.py --db data/finance.db --dashboard Dashboard.md --input "8/4 - 150 gas @wallet #transport
8/4 + 25000 freelance payout @wallet #salary"

Behavior:
  * The payload is split on newlines and each line is processed as its
    own transaction — a bad line is reported and skipped, it never
    aborts the rest of the batch.
  * Dashboard.md is regenerated exactly ONCE at the end, regardless of
    how many lines were in the payload, to minimize disk writes into
    the vault.

Exit codes:
    0  every line in the batch parsed and inserted cleanly
    1  at least one line was rejected by the parser (any lines that DID
       parse are still committed, and the dashboard still gets updated)
"""

import argparse
import sys
from pathlib import Path

from db_model import FinanceModel
from vault_controller import VaultController
from vault_view_md import VaultMarkdownView


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Vault CLI — push transactions into the finance DB and refresh Dashboard.md"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help=(
            "Transaction payload. One transaction per line, e.g. "
            "'8/4 - 150 gas @wallet #transport'. Multiple transactions "
            "are separated by newlines."
        ),
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="Path to the SQLite database file (created on first run).",
    )
    parser.add_argument(
        "--dashboard",
        required=True,
        type=Path,
        help="Path to write Dashboard.md into (e.g. your Obsidian vault folder).",
    )
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    model = FinanceModel(args.db)
    controller = VaultController(model)

    result = controller.process_batch(args.input)

    for parsed in result.inserted:
        print(f"[OK] {parsed.raw_line.strip()}")

    for err in result.errors:
        print(f"[REJECTED] {err.reason} -> {err.line.strip()}", file=sys.stderr)

    # Single write to the vault, no matter how many lines were in the
    # payload — this is the ONLY place Dashboard.md gets touched.
    view = VaultMarkdownView(args.dashboard)
    view.render(
        transactions=model.get_all_transactions_view(),
        balances=model.get_account_balances(),
        category_totals=model.get_category_totals(),
    )

    if result.had_errors:
        print(
            f"\n{len(result.inserted)} inserted, {len(result.errors)} rejected.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{len(result.inserted)} transaction(s) inserted. Dashboard updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
