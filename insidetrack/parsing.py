"""Text -> numbers, with the strict validation that keeps a misread out of a
bet. Pure functions; no OCR engine, no screen."""

import re
from typing import Optional

ODDS_RE = re.compile(r"^(EVENS|([2-9]|[12][0-9]|30)/1)$")
MONEY_RE = re.compile(r"\d+")


def clean(text: str) -> str:
    return text.strip().upper().replace(" ", "")


def parse_odds(text: str) -> Optional[int]:
    """'EVENS' -> 1, '4/1' -> 4, anything else -> None."""
    value = clean(text)
    if not ODDS_RE.match(value):
        return None
    return 1 if value == "EVENS" else int(value.split("/")[0])


def odds_label(value: Optional[int]) -> str:
    """1 -> 'EVENS', 4 -> '4/1', None -> '??'."""
    if value is None:
        return "??"
    return "EVENS" if int(value) == 1 else f"{int(value)}/1"


def repair_text(text: str) -> str:
    """Conservative fixes for characteristic drops, still validated against
    the strict pattern afterwards."""
    if text.startswith("EVEN"):
        return "EVENS"
    dropped_slash = re.match(r"^(\d{1,2})1$", text)      # '71' -> '7/1'
    if dropped_slash:
        return f"{dropped_slash.group(1)}/1"
    dropped_one = re.match(r"^(\d{1,2})/$", text)        # '7/' -> '7/1'
    if dropped_one:
        return f"{dropped_one.group(1)}/1"
    return text


def read_odds_text(text: str):
    """(value or None, text as read, repaired to what)."""
    value = parse_odds(text)
    if value is not None:
        return value, text, None
    repaired = repair_text(clean(text))
    return parse_odds(repaired), text, repaired


def parse_money(text: str) -> Optional[int]:
    """'$10,000' -> 10000. Separators are stripped only where they really are
    separators (a . or , with exactly three digits behind it), so a comma
    misread as a period does not turn $10,000 into $10."""
    digits = re.sub(r"[^\d.,]", "", text)
    digits = re.sub(r"[.,](?=\d{3}(?:\D|$))", "", digits)
    found = MONEY_RE.search(digits)
    return int(found.group()) if found else None
