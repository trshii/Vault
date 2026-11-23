import argparse
import sys
from pathlib import Path

from db_model import FinanceModel
from vault_controller import VaultController
from vault_query import QueryError
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
    parser.add_argument(
        "--query", "-q",
        default=None,
        help=(
            "Run a query instead of a normal scan/dashboard refresh. Tokens: "
            "@account, #category, a month (2026-03), a year (2026), or a month "
            "range (2026-01..2026-03; either side may be left open). "
            "Example: --query \"2026-01..2026-03 @wallet #food\". The result is "
            "written to its own file in --query-dir, named after the accounts/"
            "categories queried, and re-running overwrites that file."
        ),
    )
    parser.add_argument(
        "--query-dir",
        type=Path,
        default=None,
        help="Folder for query dashboards (default: <dashboard folder>/Queries).",
    )
    return parser


def render_query_dashboard(result, out_path: Path) -> None:
    spec = result.spec
    VaultMarkdownView(out_path).render_query(
        title=out_path.stem,
        filters=spec.describe(),
        transactions=result.transactions,
        totals=result.totals,
        category_totals=result.category_totals,
        monthly=result.monthly,
        by_account=result.by_account,
    )


def run_query_mode(args, controller: VaultController, model: FinanceModel) -> int:
    """Writes one query dashboard and returns an exit code (0 ok, 2 bad query)."""
    try:
        result = controller.run_query(args.query)
    except QueryError as e:
        print(f"[QUERY ERROR] {e}", file=sys.stderr)
        return 2

    query_dir = args.query_dir or (args.dashboard.parent / "Queries")
    out_path = query_dir / f"{result.spec.file_stem}.md"

    render_query_dashboard(result, out_path)
    # Remember it (latest query wins) so normal updates can refresh this file.
    model.save_query(str(out_path.resolve()), args.query)

    print(f"{result.totals['count']} transaction(s) matched.")
    # Machine-readable line for the Templater script, which opens this file.
    print(f"QUERY_OUTPUT: {out_path.resolve()}")
    return 0


def refresh_saved_queries(controller: VaultController, model: FinanceModel) -> int:
    """Re-runs every remembered query and rewrites its dashboard in place.
    A query whose dashboard file was deleted is forgotten, not recreated."""
    refreshed = 0
    for row in model.get_saved_queries():
        path = Path(row["filepath"])
        if not path.exists():
            model.delete_saved_query(row["filepath"])
            continue
        try:
            result = controller.run_query(row["query"])
        except QueryError as e:
            print(f"[QUERY REFRESH SKIPPED] {path.name}: {e}", file=sys.stderr)
            continue
        render_query_dashboard(result, path)
        refreshed += 1
    return refreshed


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    VAULT_ROOT_PATH = args.dashboard.parent

    args.db.parent.mkdir(parents=True, exist_ok=True)

    if args.query is not None:
        # Query mode never touches Dashboard.md or stdin; it only refreshes the DB
        # from any edited notes first so the answer is current.
        model = FinanceModel(args.db)
        controller = VaultController(model, VAULT_ROOT_PATH)
        controller.scan_vault_for_new_transactions()
        return run_query_mode(args, controller, model)

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

    refreshed = refresh_saved_queries(controller, model)
    if refreshed:
        print(f"Refreshed {refreshed} query dashboard(s).")

    print(f"\nVault scan complete. Dashboard updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())