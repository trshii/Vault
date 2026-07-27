import re
from typing import Any, List, Dict, Optional

def parse_financial_notes(raw_text: str) -> List[Dict[str, Any]]:
    parsed_data: List[Dict[str, Any]] = []
    
    # Regex breakdown:
    # ([+-]?\s*\d+(?:\.\d+)?) -> Captures sign, optional space, digits, optional decimals (the amount)
    # \s+                      -> Expects at least one space between amount and description
    # (.+?)                    -> Captures the description, as few characters as possible (lazy)
    # (?:\s*@(\S+))?           -> Optional trailing "@account" tag, e.g. "-264 gas @cash".
    #                             The account is a single word (no spaces) so it doesn't eat
    #                             into the description; omit it and account comes back as None.
    # $                        -> Anchors the optional tag to the end of this transaction chunk,
    #                             which is what forces the lazy (.+?) to stop right before "@..."
    #                             instead of swallowing the whole remainder.
    pattern = re.compile(r'([+-]?\s*\d+(?:\.\d+)?)\s+(.+?)(?:\s*@(\S+))?$')
    
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
            match = pattern.search(trans)
            
            if match:
                # 3. Clean and convert the extracted data
                raw_amount = match.group(1).replace(' ', '') # Turns "- 20" into "-20"
                amount = float(raw_amount)
                description = match.group(2).strip()
                account: Optional[str] = match.group(3)  # None if no "@account" tag was given
                
                parsed_data.append({
                    "date": date,
                    "amount": amount,
                    "description": description,
                    "account": account
                })
                
    return parsed_data
