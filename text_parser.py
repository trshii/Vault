import re
from typing import Any, List, Dict, Optional

def parse_financial_notes(raw_text: str) -> List[Dict[str, Any]]:
    parsed_data: List[Dict[str, Any]] = []

    # Regex breakdown:
    # ^([+-]?\s*\d+(?:\.\d+)?) -> Captures sign, optional space, digits, optional decimals (the amount)
    # \s+                      -> Expects at least one space between amount and everything else
    # (.+)$                    -> Captures the remainder of the transaction chunk: the description
    #                             plus any trailing @account / #category tags, which get peeled
    #                             off separately below.
    amount_pattern = re.compile(r'^([+-]?\s*\d+(?:\.\d+)?)\s+(.+)$')

    # Matches ONE trailing tag - either "@account" or "#category" - anchored to
    # the end of whatever string it's run against via `$`. Tags are single
    # words (no spaces), same convention as the original @account tag, so a
    # tag never eats into the description. Re-running this against the
    # shrinking remainder (see the loop below) lets @account and #category
    # show up in either order, since each pass just strips whichever tag is
    # currently last.
    trailing_tag_pattern = re.compile(r'\s*([@#])(\S+)$')

    lines = raw_text.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 1. Separate Date from Transactions
        if ' - ' not in line:
            continue

        date_part, transactions_part = line.split(' - ', 1)
        date = date_part.strip()

        # 2. Handle multiple transactions on one line
        transactions = transactions_part.split(',')

        for trans in transactions:
            trans = trans.strip()
            match = amount_pattern.match(trans)

            if not match:
                continue

            # 3. Clean and convert the extracted amount
            raw_amount = match.group(1).replace(' ', '')  # Turns "- 20" into "-20"
            amount = float(raw_amount)
            remainder = match.group(2).strip()

            # 4. Peel off up to two trailing tags (one @account, one #category,
            #    in either order). Whatever's left after that is the description.
            account: Optional[str] = None
            category: Optional[str] = None

            for _ in range(2):
                tag_match = trailing_tag_pattern.search(remainder)
                if not tag_match:
                    break
                marker, value = tag_match.group(1), tag_match.group(2)
                remainder = remainder[:tag_match.start()].strip()
                if marker == '@' and account is None:
                    account = value
                elif marker == '#' and category is None:
                    category = value

            description = remainder

            parsed_data.append({
                "date": date,
                "amount": amount,
                "description": description,
                "account": account,      # None if no "@account" tag was given
                "category": category,    # None if no "#category" tag was given
            })

    return parsed_data
