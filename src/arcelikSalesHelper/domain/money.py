"""Parsing of user-entered money text.  Never raises for bad user input.

Disambiguation rules
--------------------
* Both '.' and ',' present: the LAST separator is the decimal mark, the other
  kind is the thousands separator and must form valid groups.
* Only ',': decimal mark (exactly one allowed).
* Only '.':
    - more than once: must be valid thousands grouping (1.234.567);
    - once: if it looks like a thousands group (1-3 digits, not starting with 0,
      then exactly 3 digits) it is THOUSANDS ("54.999" -> 54999, Turkish
      convention) and the result is flagged ``ambiguous`` so the UI can show a
      hint.  Otherwise it is a decimal point ("54999.00", "12.5", "0.500").
* Optional trailing TL / TRY and surrounding whitespace are stripped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from .result import Err, Ok, Result

_TL_SUFFIX = re.compile(r"\s*(?:TL|TRY)\s*$", re.IGNORECASE)
_ALLOWED = re.compile(r"[0-9.,]+")
_DIGITS = re.compile(r"[0-9]+")
_GROUPED_DOT = re.compile(r"[1-9][0-9]{0,2}(?:\.[0-9]{3})+")
_GROUPED_COMMA = re.compile(r"[1-9][0-9]{0,2}(?:,[0-9]{3})+")
_MAX_LEN = 40

_MSG_EMPTY = "Enter an amount."
_MSG_NEGATIVE = "Negative amounts are not allowed."
_MSG_CHARS = (
    "Use digits with '.' or ',' separators only (for example 54.999,00)."
)
_MSG_FORMAT = "Invalid number format."
_MSG_GROUPING = "Invalid thousands grouping (for example 1.234.567,89)."
_MSG_COMMAS = "Only one decimal comma is allowed."
_MSG_LONG = "Amount is too long."


@dataclass(frozen=True)
class ParsedMoney:
    value: Decimal
    # True for a single '.' followed by exactly 3 digits ("1.234"), which was
    # read as a thousands separator.  The UI should show a hint.
    ambiguous: bool = False


def _decimal(text: str, mark: str) -> Result[ParsedMoney, str]:
    int_part, _, frac = text.partition(mark)
    if not _DIGITS.fullmatch(int_part) or not _DIGITS.fullmatch(frac):
        return Err(_MSG_FORMAT)
    return Ok(ParsedMoney(Decimal(f"{int_part}.{frac}")))


def parse_money_ex(text: str) -> Result[ParsedMoney, str]:
    s = _TL_SUFFIX.sub("", text.strip()).strip()
    if not s:
        return Err(_MSG_EMPTY)
    if s.startswith("-"):
        return Err(_MSG_NEGATIVE)
    if len(s) > _MAX_LEN:
        return Err(_MSG_LONG)
    if not _ALLOWED.fullmatch(s):
        return Err(_MSG_CHARS)

    has_dot = "." in s
    has_comma = "," in s

    if not has_dot and not has_comma:
        return Ok(ParsedMoney(Decimal(s)))

    if has_dot and has_comma:
        dec, thousands_re = (
            (",", _GROUPED_DOT)
            if s.rfind(",") > s.rfind(".")
            else (".", _GROUPED_COMMA)
        )
        int_part, _, frac = s.rpartition(dec)
        if not _DIGITS.fullmatch(frac):
            return Err(_MSG_FORMAT)
        if not thousands_re.fullmatch(int_part):
            return Err(_MSG_GROUPING)
        sep = "." if dec == "," else ","
        return Ok(ParsedMoney(Decimal(f"{int_part.replace(sep, '')}.{frac}")))

    if has_comma:
        if s.count(",") > 1:
            return Err(_MSG_COMMAS)
        return _decimal(s, ",")

    # dots only
    if _GROUPED_DOT.fullmatch(s):
        return Ok(
            ParsedMoney(
                Decimal(s.replace(".", "")), ambiguous=s.count(".") == 1
            )
        )
    if s.count(".") > 1:
        return Err(_MSG_GROUPING)
    return _decimal(s, ".")


def parse_money(text: str) -> Result[Decimal, str]:
    match parse_money_ex(text):
        case Ok(parsed):
            return Ok(parsed.value)
        case Err(message):
            return Err(message)
    raise AssertionError("unreachable")  # pragma: no cover
