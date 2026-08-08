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
        required=False,
        default=None,
        help=(
            "Transaction payload. One transaction per line, e.g. "
            "'8/4 - 150 gas @wallet #transport'. Multiple transactions "
            "are separated by newlines. If omitted, the payload is read "
            "from stdin instead — the more robust option for callers "
            "(Templater, etc.) that would otherwise have to smuggle a "
            "multi-line string through a shell command line."
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
    VAULT_ROOT_PATH = args.dashboard.parent

    args.db.parent.mkdir(parents=True, exist_ok=True)
    
    if not args.dashboard.exists():
        print(f"Dashboard not found at {args.dashboard}. Creating a new one...")
        args.dashboard.parent.mkdir(parents=True, exist_ok=True)
        
        default_dashboard = (
            "# Financial Dashboard\n\n"
            "> This dashboard is automatically updated by Vault.\n\n"
            "%% VAULT_START %%\n"
            "*Charts will appear here after your first update...*\n"
            "%% VAULT_END %%\n"
        )
        args.dashboard.write_text(default_dashboard, encoding="utf-8")

    raw_input = ""
    if args.input is not None:
        raw_input = args.input
    elif not sys.stdin.isatty(): 
        raw_input = sys.stdin.read()

    model = FinanceModel(args.db)
    controller = VaultController(model, VAULT_ROOT_PATH)

    controller.scan_vault_for_new_transactions()

    result = None
    if raw_input.strip():
        result = controller.process_batch(raw_input)
        for parsed in result.inserted:
            print(f"[OK] {parsed.raw_line.strip()}")
        for err in result.errors:
            print(f"[REJECTED] {err.reason} -> {err.line.strip()}", file=sys.stderr)

    recent_files = model.get_recently_processed_files(limit=5)
    
    view = VaultMarkdownView(args.dashboard)
    view.render(
        transactions=model.get_all_transactions_view(),
        balances=model.get_account_balances(),
        category_totals=model.get_category_totals(),
        recent_files=recent_files
    )

    print(f"\nVault scan complete. Dashboard updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())