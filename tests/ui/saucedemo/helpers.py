import re
from decimal import Decimal

def money(text):
    match = re.fullmatch(r"\$(\d+\.\d{2})", text.strip())
    if not match:
        raise ValueError("Expected a USD amount with two decimal places")
    return Decimal(match[1])

def label_money(text, prefix):
    if not text.startswith(prefix):
        raise ValueError("Unexpected monetary label")
    return money(text[len(prefix):].strip())
