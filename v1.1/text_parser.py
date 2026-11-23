import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


class ParserError(ValueError):
    """Raised when a single line can't be turned into a valid transaction."""

    def __init__(self, line: str, reason: str):
        self.line = line
        self.reason = reason
        super().__init__(f"{reason} | line: {line!r}")


@dataclass
class ParsedTransaction:
    date: str
    amount: float                 
    description: str
    account: str                  
    category: Optional[str]       
    raw_line: str


LINE_PATTERN = re.compile(
    r'^(?:(?P<date>\d{1,2}/\d{1,2})\s+)?(?P<sign>[+-])\s*(?P<amount>\d+(?:\.\d+)?)\s+(?P<rest>.+)$'
)

TRAILING_TAG_PATTERN = re.compile(r'\s*([@#])(\S+)$')


def parse_transaction_line(line: str, fallback_date: str) -> ParsedTransaction:
    """
    Parses a single line into a ParsedTransaction.

    fallback_date must be a zero-padded 'YYYY-MM-DD' string. It's used
    verbatim when the line has no inline date, and as the source of the
    year when the line's inline date only gives month/day (e.g. '8/4') —
    inline dates never carry a year, so one has to come from somewhere.

    Raises ParserError if:
      - the line doesn't match the '[date] <sign> <amount> <description>' shape
      - the description ends up empty after tags are peeled off
      - no @account tag is present
    """
    raw_line = line
    line = line.strip()

    if not line:
        raise ParserError(raw_line, "Empty line")

    match = LINE_PATTERN.match(line)
    if not match:
        raise ParserError(
            raw_line,
            "Doesn't match '[date] <sign> <amount> <description...>' format",
        )

    extracted_date = match.group("date")
    if extracted_date:
        fallback_year = fallback_date.split("-")[0]
        month_str, day_str = extracted_date.strip().split("/")
        date = f"{fallback_year}-{int(month_str):02d}-{int(day_str):02d}"
    else:
        date = fallback_date
    
    sign = match.group("sign")
    amount = float(match.group("amount"))
    if sign == "-":
        amount = -amount

    remainder = match.group("rest").strip()

    account: Optional[str] = None
    category: Optional[str] = None

    for _ in range(2):
        tag_match = TRAILING_TAG_PATTERN.search(remainder)
        if not tag_match:
            break
        marker, value = tag_match.group(1), tag_match.group(2)
        remainder = remainder[: tag_match.start()].strip()
        if marker == "@" and account is None:
            account = value
        elif marker == "#" and category is None:
            category = value

    description = remainder
    if not description:
        raise ParserError(raw_line, "Missing description")

    if account is None:
        raise ParserError(
            raw_line,
            "Missing required @account tag — every transaction must name an account",
        )

    return ParsedTransaction(
        date=date,
        amount=amount,
        description=description,
        account=account,
        category=category,
        raw_line=raw_line,
    )


def parse_batch(raw_text: str, fallback_date: str) -> Tuple[List[ParsedTransaction], List[ParserError]]:
    """
    Parses a multi-line payload, one transaction per line. Each line is
    parsed independently — a malformed or under-tagged line is collected
    as an error and does NOT stop the rest of the batch from processing.

    fallback_date must be a zero-padded 'YYYY-MM-DD' string (see
    parse_transaction_line for how it's used).

    Returns (successfully_parsed, errors), in original line order within
    each list.
    """
    successes: List[ParsedTransaction] = []
    errors: List[ParserError] = []

    for line in raw_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            successes.append(parse_transaction_line(line, fallback_date))
        except ParserError as e:
            errors.append(e)

    return successes, errors