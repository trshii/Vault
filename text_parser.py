"""
text_parser.py
---------------
Strict, single-transaction-per-line parser for the shorthand format:

    <date> <sign> <amount> <description> [@account] [#category]

Example:
    8/4 - 150 gas for giorno+ @wallet #transport
    8/4 + 25000 freelance payout @wallet #salary

The parser is the ultimate gatekeeper for data integrity:

  * @account is REQUIRED. A line with no account tag raises ParserError
    rather than being guessed at — money has to go *somewhere*
    identifiable, and there's no reasonable default account to fall
    back to.
  * #category is OPTIONAL. A line with no category tag still parses
    successfully; `category` comes back as None and it's the
    Controller's job to route it into the appropriate "Uncategorized"
    bucket (see vault_controller.py).

Parsing one line never blows up the whole batch — parse_batch() catches
ParserError per-line and keeps going.
"""

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
    amount: float                  # already signed: negative for outflow
    description: str
    account: str                   # always present (parser enforces this)
    category: Optional[str]        # None => caller must use an Uncategorized bucket
    raw_line: str


# ---------------------------------------------------------------------------
# Regex breakdown
# ---------------------------------------------------------------------------
# ^(?P<date>\S+)             -> date token, e.g. "8/4" (no internal spaces)
# \s+(?P<sign>[+-])\s*       -> the sign. Space BEFORE it is required (it's
#                               what separates it from the date); space
#                               AFTER it is optional, so both "- 150" and
#                               "-150" parse the same way.
# (?P<amount>\d+(?:\.\d+)?)  -> the unsigned numeric amount
# \s+(?P<rest>.+)$           -> everything else: description + any trailing
#                               @account / #category tags, peeled off below.
LINE_PATTERN = re.compile(
    r'^(?P<date>\S+)\s+(?P<sign>[+-])\s*(?P<amount>\d+(?:\.\d+)?)\s+(?P<rest>.+)$'
)

# Matches ONE trailing tag ("@word" or "#word") anchored to the end of the
# string via `$`. Run in a loop (see below) so @account and #category can
# appear in either order — each pass just strips whichever tag is last.
TRAILING_TAG_PATTERN = re.compile(r'\s*([@#])(\S+)$')


def parse_transaction_line(line: str) -> ParsedTransaction:
    """
    Parses a single line into a ParsedTransaction.

    Raises ParserError if:
      - the line doesn't match the '<date> <sign> <amount> <description>' shape
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
            "Doesn't match '<date> <sign> <amount> <description...>' format",
        )

    date = match.group("date").strip()
    sign = match.group("sign")
    amount = float(match.group("amount"))
    if sign == "-":
        amount = -amount

    remainder = match.group("rest").strip()

    # Peel off up to two trailing tags (one @account, one #category, in
    # either order). Whatever's left after that is the description.
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

    # --- Strict gate: @account is mandatory, no silent fallback ---
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
        category=category,  # legitimately None if untagged
        raw_line=raw_line,
    )


def parse_batch(raw_text: str) -> Tuple[List[ParsedTransaction], List[ParserError]]:
    """
    Parses a multi-line payload, one transaction per line. Each line is
    parsed independently — a malformed or under-tagged line is collected
    as an error and does NOT stop the rest of the batch from processing.

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
            successes.append(parse_transaction_line(line))
        except ParserError as e:
            errors.append(e)

    return successes, errors
