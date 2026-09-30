"""Lecture d'un montant affiché par une source, sans rien deviner.

Un montant est un texte écrit par un tiers : « £3,500 », « CHF 7,750 »,
« € 1.520 ». La virgule et le point y sont tantôt séparateur de milliers, tantôt
de décimales, selon la langue de la source. En cas de doute le montant est
refusé (`None`) : un montant faux entre dans la cote, un montant absent n'y
entre pas.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_SYMBOLS = {"£": "GBP", "€": "EUR"}
_CODE = re.compile(r"\b([A-Z]{3})\b")
_NUMBER = re.compile(r"\d[\d.,\u00a0\u202f ]*\d|\d")


def _to_decimal(raw: str) -> Decimal | None:
    number = re.sub(r"[\u00a0\u202f ]", "", raw)
    # « 1,520 » ou « 1.520 » : trois chiffres après le séparateur, un seul
    # séparateur de ce type → milliers. « 1,520.50 » : virgule = milliers.
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", number):
        number = re.sub(r"[.,]", "", number)
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d{1,2}", number):
        number = number.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{1,2}", number):
        number = number.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", number):
        number = number.replace(",", ".")
    elif not re.fullmatch(r"\d+(?:\.\d{1,2})?", number):
        return None
    try:
        value = Decimal(number)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def parse_amount(
    text: str, default_currency: str | None = None
) -> tuple[Decimal, str] | None:
    """`(montant, devise)` ou `None`. La devise vient d'un symbole ou d'un code
    ISO présent dans le texte ; sans l'un ni l'autre, `default_currency`. Le
    symbole « $ » est ambigu (USD, HKD, CAD…) : il n'est jamais interprété."""

    if "$" in text and not _CODE.search(text):
        return None
    currency: str | None = None
    for symbol, code in _SYMBOLS.items():
        if symbol in text:
            currency = code
    code_match = _CODE.search(text)
    if code_match:
        currency = code_match.group(1)
    currency = currency or default_currency
    if currency is None:
        return None
    number = _NUMBER.search(text)
    if number is None:
        return None
    amount = _to_decimal(number.group(0))
    return (amount, currency) if amount is not None else None
