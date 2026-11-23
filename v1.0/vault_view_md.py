from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class VaultMarkdownView:
    def __init__(self, output_path: Path):
        self.output_path = output_path

    @staticmethod
    def _escape_cell(value: Any) -> str:
        """Makes free-text safe to drop into a markdown table cell.

        Without this, a description or tag containing a literal '|'
        (e.g. '-50 lunch | groceries @wallet') silently breaks that row's
        column alignment for the rest of the table.
        """
        text = "" if value is None else str(value)
        return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        
    def _build_inflow_outflow_pie_chart(self, category_totals: List[Dict[str, Any]]) -> List[str]:
        """Generates an Obsidian chart code block for total inflow vs total outflow."""
        if not category_totals:
            return ["> [!warning] Pie Chart: No category data found in SQLite."]

        inflow_total = sum(row["total"] for row in category_totals if row["type"] == "inflow")
        outflow_total = sum(row["total"] for row in category_totals if row["type"] == "outflow")

        labels = ["Inflow", "Outflow"]
        data = [str(abs(inflow_total)), str(abs(outflow_total))]
        bg_colors = ["'#4bc0c0'", "'#ff6384'"]  # green for inflow, red for outflow

        return [
            "```chart",
            "type: pie",
            f"labels: [{', '.join(labels)}]",
            "series:",
            "  - title: Inflow vs Outflow",
            f"    data: [{', '.join(data)}]",
            f"    backgroundColor: [{', '.join(bg_colors)}]",
            "    borderWidth: 0",
            "    width: 100%",
            "```",
            ""
        ]
        
    def _build_balance_bar_chart(self, balances: List[Dict[str, Any]]) -> List[str]:
        """Generates an Obsidian chart code block showing liquidity across accounts."""
        
        if not balances:
            return ["*No account data yet. Log a transaction to generate your charts!*", ""]
    
        labels = [row['account'].title() for row in balances]
        data = [str(row['balance']) for row in balances]
        data_count = len(data)
        bg_colors = []
                
        palette = ["#ff6384", "#36a2eb", "#cc65fe", "#ffce56", "#4bc0c0", "#9966ff", "#ff9f40"]
        
        lowest_balance = min(float(row['balance']) for row in balances)
        y_axis_min = max(0, int(lowest_balance * 0.8))
        
        for i in range(data_count):
            color = f"'{palette[i % len(palette)]}'"
            bg_colors.append(color)
        
        if not labels:
            return []
            
        return [
            "```chart",
            "type: bar",
            f"labels: [{', '.join(labels)}]",
            "series:",
            "  - title: Current Balance",
            f"    data: [{', '.join(data)}]",
            f"    backgroundColor: [{', '.join(bg_colors)}]",
             "    borderWidth: 0", 
            f"yMin: {y_axis_min}",
            "transparency: 1.0",
            "```",
            ""
        ]
        
    def _build_category_breakdown_charts(self, category_totals: List[Dict[str, Any]]) -> List[str]:
        """Generates two Obsidian pie charts: what categories make up
        inflow, and what categories make up outflow.

        This is a different view than _build_inflow_outflow_pie_chart, which
        only shows a single two-slice pie (total inflow vs. total outflow).
        This one shows the composition *within* each side.

        A single shared-axis chart (e.g. one grouped bar chart) was tried
        instead to sidestep Obsidian's side-by-side layout limitations, but
        it has a real analytical downside: a small category (e.g. a $30
        coffee run) becomes visually invisible next to a large one (e.g. a
        $1000 paycheck) on a shared axis. Pies don't have that problem —
        each pie's slices are proportional only to its own total, not to
        the other chart's scale. The Charts plugin also has no logarithmic
        axis option to work around this (see phibr0/obsidian-charts#57,
        an open, unimplemented feature request), so pies are the better
        fit for this data even though it costs the single-block simplicity.

        LAYOUT NOTE: side-by-side placement was tried via both a raw HTML
        flex wrapper and a CSS snippet targeting adjacent chart blocks;
        neither reliably worked in Reading view or Live Preview, since each
        rendered chart occupies its own block/line in the document flow
        regardless of its own `display` property. These render as two
        plain, ordinary, stacked chart blocks instead — guaranteed to
        actually render, just not side by side.
        """
        # Two distinct color families instead of one shared palette — this
        # matches the teal/red convention _build_inflow_outflow_pie_chart
        # already uses, and prevents e.g. slice #1 of each pie coincidentally
        # sharing the same color, which reads as "these are the same
        # category" even though they're unrelated.
        inflow_palette = ["#4bc0c0", "#36a2eb", "#2ecc71", "#1abc9c", "#3498db", "#16a085", "#27ae60"]
        outflow_palette = ["#ff6384", "#ff9f40", "#e74c3c", "#e67e22", "#cc65fe", "#f39c12", "#d35400"]

        def _pie_block(rows: List[Dict[str, Any]], title: str, palette: List[str]) -> str:
            if not rows:
                return f"*No {title.lower()} recorded yet.*"

            labels = [row["category"].title() for row in rows]
            data = [str(abs(row["total"])) for row in rows]
            colors = [f"'{palette[i % len(palette)]}'" for i in range(len(rows))]

            return "\n".join([
                "```chart",
                "type: pie",
                f"labels: [{', '.join(labels)}]",
                "series:",
                f"  - title: {title}",
                f"    data: [{', '.join(data)}]",
                f"    backgroundColor: [{', '.join(colors)}]",
                "    borderWidth: 0",
                "    width: 100%",
                "```",
            ])

        # Zero-total categories (e.g. an untouched Uncategorized bucket)
        # would render as a useless slice, so they're filtered out.
        inflow_rows = [r for r in category_totals if r["type"] == "inflow" and r["total"] != 0]
        outflow_rows = [r for r in category_totals if r["type"] == "outflow" and r["total"] != 0]

        if not inflow_rows and not outflow_rows:
            return ["> [!warning] Category Breakdown: No category data found in SQLite.", ""]

        inflow_block = _pie_block(inflow_rows, "Inflow by Category", inflow_palette)
        outflow_block = _pie_block(outflow_rows, "Outflow by Category", outflow_palette)

        return [
            inflow_block,
            "",
            outflow_block,
            "",
        ]

    def _build_recent_files_section(self, recent_files: List[str]) -> List[str]:
        """Generates a markdown list of wikilinks for recently processed files."""
        if not recent_files:
            return ["> [!info] No recently processed files found.", ""]

        lines = ["### Recently Processed Notes", ""]
        for filepath in recent_files:
            filename = Path(filepath).stem
            lines.append(f"* [[{filename}]]")
            
        lines.append("")
        return lines

    def render(
        self,
        transactions: List[Dict[str, Any]],
        balances: List[Dict[str, Any]],
        category_totals: List[Dict[str, Any]],
        recent_files: List[str]
    ) -> None:
        """Builds Dashboard.md in memory, then writes it in a single pass."""
        lines: List[str] = []

        lines.append("# Vault Dashboard")
        lines.append(f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")
        
        lines.append("## Liquidity")
        lines.extend(self._build_balance_bar_chart(balances))
        lines.append("")
        
        lines.append("## Financial Overview")
        lines.extend(self._build_inflow_outflow_pie_chart(category_totals))
        lines.append("")

        lines.append("## Category Breakdown")
        lines.extend(self._build_category_breakdown_charts(category_totals))
        lines.append("")

        lines.append("## Account Balances")
        lines.append("| Account | Balance |")
        lines.append("|---|---:|")
        total_balance = 0
        for row in balances:
            account = self._escape_cell(row['account'].title())
            lines.append(f"| {account} | {row['balance']:.2f} |")
            total_balance += row['balance']
        lines.append(f"| Total: | {total_balance:.2f} |")
        lines.append("")

        lines.append("## Category Totals")
        lines.append("| Category | Type | Total |")
        lines.append("|---|---|---:|")
        for row in category_totals:
            category = self._escape_cell(row['category'].title())
            tx_type = self._escape_cell(row['type'].title())
            lines.append(f"| {category} | {tx_type} | {row['total']:.2f} |")
        lines.append("")

        lines.append("## Transactions")
        lines.append("| Date | Amount | Type | Category | Account | Description |")
        lines.append("|---|---:|---|---|---|---|")
        for row in transactions:
            tx_type = self._escape_cell(row['type'])
            category = self._escape_cell(row['category'].title())
            account = self._escape_cell(row['account'].title())
            description = self._escape_cell(row['description'])
            lines.append(
                f"| {row['date']} | {row['amount']:.2f} | {tx_type} | "
                f"{category} | {account} | {description} |"
            )
        lines.append("")
        
        lines.extend(self._build_recent_files_section(recent_files))

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("\n".join(lines), encoding="utf-8")