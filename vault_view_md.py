"""
vault_view_md.py
-----------------
View layer (MVC) for the Obsidian integration.

Unlike the old VaultTmnlView, this view never reads anything — it only
renders one markdown file, Dashboard.md, from whatever the Model hands
it, and writes ("pushes") that file into the vault. SQLite stays the
single source of truth; Obsidian only ever displays a generated
snapshot.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class VaultMarkdownView:
    def __init__(self, output_path: Path):
        self.output_path = output_path

    def render(
        self,
        transactions: List[Dict[str, Any]],
        balances: List[Dict[str, Any]],
        category_totals: List[Dict[str, Any]],
    ) -> None:
        """Builds Dashboard.md in memory, then writes it in a single pass."""
        lines: List[str] = []

        lines.append("# Vault Dashboard")
        lines.append(f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

        lines.append("## Account Balances")
        lines.append("| Account | Balance |")
        lines.append("|---|---:|")
        for row in balances:
            lines.append(f"| {row['account']} | {row['balance']:.2f} |")
        lines.append("")

        lines.append("## Category Totals")
        lines.append("| Category | Type | Total |")
        lines.append("|---|---|---:|")
        for row in category_totals:
            lines.append(f"| {row['category']} | {row['type']} | {row['total']:.2f} |")
        lines.append("")

        lines.append("## Transactions")
        lines.append("| Date | Amount | Type | Category | Account | Description |")
        lines.append("|---|---:|---|---|---|---|")
        for row in transactions:
            lines.append(
                f"| {row['date']} | {row['amount']:.2f} | {row['type']} | "
                f"{row['category']} | {row['account']} | {row['description']} |"
            )
        lines.append("")

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("\n".join(lines), encoding="utf-8")
