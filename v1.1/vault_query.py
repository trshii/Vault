import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


class QueryError(ValueError):
    """Raised when a query string can't be understood."""


# A "period" is a year ('2026') or a month ('2026-03').
_PERIOD = r"\d{4}(?:-\d{2})?"
_SINGLE_RE = re.compile(rf"^({_PERIOD})$")
_RANGE_RE = re.compile(rf"^({_PERIOD})?\.\.({_PERIOD})?$")


def _month_start(period: str) -> Tuple[int, int]:
    parts = period.split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) == 2 else 1
    if not 1 <= month <= 12:
        raise QueryError(f"Invalid month in {period!r}")
    return year, month


def _period_end_exclusive(period: str) -> Tuple[int, int]:
    """First (year, month) AFTER the period: '2026-03' -> (2026, 4), '2026' -> (2027, 1)."""
    year, month = _month_start(period)
    if "-" not in period:
        return year + 1, 1
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _iso(ym: Tuple[int, int]) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}-01"


def _parse_period_token(token: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (start_inclusive, end_exclusive) as 'YYYY-MM-01' strings (either may be None)."""
    single = _SINGLE_RE.match(token)
    if single:
        period = single.group(1)
        return _iso(_month_start(period)), _iso(_period_end_exclusive(period))

    ranged = _RANGE_RE.match(token)
    if ranged and (ranged.group(1) or ranged.group(2)):
        left, right = ranged.groups()
        start = _iso(_month_start(left)) if left else None
        end = _iso(_period_end_exclusive(right)) if right else None
        if start and end and start >= end:
            raise QueryError(f"Range {token!r} ends before it starts")
        return start, end

    raise QueryError(
        f"Don't understand {token!r} — use YYYY-MM, YYYY, or a range like "
        f"2026-01..2026-03 (either side may be left open)"
    )


def _dedupe(values: List[str]) -> Tuple[str, ...]:
    seen, out = set(), []
    for v in values:
        if v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return tuple(out)


@dataclass(frozen=True)
class QuerySpec:
    accounts: Tuple[str, ...]
    categories: Tuple[str, ...]
    start: Optional[str]          # inclusive, 'YYYY-MM-01'
    end: Optional[str]            # EXCLUSIVE, 'YYYY-MM-01'
    raw: str

    @property
    def file_stem(self) -> str:
        """Output filename (no extension). Depends ONLY on accounts + categories,
        so re-running a query with a different date range rewrites the same file."""
        parts = []
        if self.accounts:
            parts.append("acct " + "+".join(sorted(a.lower() for a in self.accounts)))
        if self.categories:
            parts.append("cat " + "+".join(sorted(c.lower() for c in self.categories)))
        stem = "Query - " + (", ".join(parts) if parts else "all")
        # '#', '[', ']', '^' break Obsidian wikilinks; the rest break filesystems.
        stem = re.sub(r'[<>:"/\\|?*#^\[\]]', "_", stem)
        # Never let a query file look like a daily note to scan_vault_for_new_transactions().
        return re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", stem)

    @property
    def period_label(self) -> str:
        if not self.start and not self.end:
            return "All time"
        first = self.start[:7] if self.start else "earliest"
        if self.end:
            y, m = int(self.end[:4]), int(self.end[5:7])
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
            last = f"{y:04d}-{m:02d}"
        else:
            last = "latest"
        return first if first == last else f"{first} → {last}"

    def describe(self) -> List[str]:
        lines = [f"Query: `{self.raw.strip() or '(everything)'}`", f"Period: {self.period_label}"]
        if self.accounts:
            lines.append("Accounts: " + ", ".join(self.accounts))
        if self.categories:
            lines.append("Categories: " + ", ".join(self.categories))
        return lines


def parse_query(text: str) -> QuerySpec:
    """
    Grammar (tokens are whitespace-separated, order doesn't matter):
        @account          repeatable, OR'd together
        #category         repeatable, OR'd together
        2026-03           one month
        2026              one whole year
        2026-01..2026-03  inclusive month range; either side may be omitted
                          ('2026-06..' = June 2026 onwards, '..2026-03' = up to March)
        '2026-01 to 2026-03' is accepted as a synonym for '..'
    Accounts, categories and the period are AND'd together.
    """
    normalized = re.sub(r"\s+to\s+", "..", text.strip(), flags=re.IGNORECASE)
    normalized = re.sub(r"\s*\.\.\s*", "..", normalized)

    accounts: List[str] = []
    categories: List[str] = []
    start = end = None
    seen_period = False

    for token in normalized.split():
        marker, value = token[0], token[1:]
        if marker in "@#":
            if not value:
                raise QueryError(f"Empty tag {token!r}")
            (accounts if marker == "@" else categories).append(value)
        else:
            if seen_period:
                raise QueryError("Only one month or month range per query")
            seen_period = True
            start, end = _parse_period_token(token)

    return QuerySpec(_dedupe(accounts), _dedupe(categories), start, end, text)


def _month_span(first: str, last: str) -> List[str]:
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregates filtered transaction rows. Inflow/outflow is decided by the
    sign of each transaction's amount, so a category used both ways splits cleanly.

    category_totals is shaped like FinanceModel.get_category_totals() so the
    existing pie-chart builders can consume it unchanged.
    """
    totals = {"inflow": 0.0, "outflow": 0.0, "net": 0.0, "count": len(rows)}
    cats: Dict[Tuple[str, str], float] = {}
    months: Dict[str, Dict[str, float]] = {}
    accts: Dict[str, Dict[str, float]] = {}

    for r in rows:
        amount = r["amount"]
        side = "inflow" if amount > 0 else "outflow"
        totals[side] += amount
        cats[(r["category"], side)] = cats.get((r["category"], side), 0.0) + amount
        months.setdefault(r["date"][:7], {"inflow": 0.0, "outflow": 0.0})[side] += amount
        accts.setdefault(r["account"], {"inflow": 0.0, "outflow": 0.0})[side] += amount

    totals["net"] = totals["inflow"] + totals["outflow"]

    category_totals = [
        {"category": c, "type": t, "total": v}
        for (c, t), v in sorted(cats.items(), key=lambda kv: (kv[0][1], kv[0][0].lower()))
    ]

    monthly: List[Dict[str, Any]] = []
    if months:
        for month in _month_span(min(months), max(months)):   # fills empty months in between
            m = months.get(month, {"inflow": 0.0, "outflow": 0.0})
            monthly.append({"month": month, **m, "net": m["inflow"] + m["outflow"]})

    by_account = [
        {"account": a, **v, "net": v["inflow"] + v["outflow"]}
        for a, v in sorted(accts.items(), key=lambda kv: kv[0].lower())
    ]

    return {
        "totals": totals,
        "category_totals": category_totals,
        "monthly": monthly,
        "by_account": by_account,
    }
