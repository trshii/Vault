from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class VaultMarkdownView:
    def __init__(self, output_path: Path):
        self.output_path = output_path
        
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
            return "*No account data yet. Log a transaction to generate your charts!*"
    
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

        lines.append("## Account Balances")
        lines.append("| Account | Balance |")
        lines.append("|---|---:|")
        total_balance = 0
        for row in balances:
            lines.append(f"| {row['account'].title()} | {row['balance']:.2f} |")
            total_balance += row['balance']
        lines.append(f"| Total: | {total_balance:.2f} |")
        lines.append("")

        lines.append("## Category Totals")
        lines.append("| Category | Type | Total |")
        lines.append("|---|---|---:|")
        for row in category_totals:
            lines.append(f"| {row['category'].title()} | {row['type'].title()} | {row['total']:.2f} |")
        lines.append("")

        lines.append("## Transactions")
        lines.append("| Date | Amount | Type | Category | Account | Description |")
        lines.append("|---|---:|---|---|---|---|")
        for row in transactions:
            lines.append(
                f"| {row['date']} | {row['amount']:.2f} | {row['type']} | "
                f"{row['category'].title()} | {row['account'].title()} | {row['description']} |"
            )
        lines.append("")
        
        lines.extend(self._build_recent_files_section(recent_files))

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("\n".join(lines), encoding="utf-8")
