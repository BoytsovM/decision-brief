"""Selective counterparty list for one company.

The payment file has one row per aggregated link. This module does not
build or draw that graph. It keeps the rows of a single company.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

# A payment at or above one trillion rubles is the known spike.
# It is left out before any share is calculated.
_TRILLION_RUB = 1_000_000_000_000
_MIN_SHARE = 0.10


@dataclass(frozen=True)
class CounterpartyShare:
    """One other company and its weight in the payment sum.

    ``share`` is a fraction of the company payment sum, so 0.10 is 10%.
    There is no foreign-trade direction: the payment file does not say
    whether a link is import or export.
    """

    counterparty_id: str
    amount_rub: float
    payment_count: int
    share: float


def counterparties_for_company(
    company_id: str,
    payments_path: Path,
    companies_path: Path,
) -> list[CounterpartyShare]:
    """Return counterparties of one company, largest share first.

    A link is shown when both parties are in the company directory and
    its amount is at least 10% of that company's payment sum. The sum
    counts every payment where the company is payer or beneficiary,
    including a self-payment and a payment to an id outside the
    directory. An amount of one trillion rubles or more is removed
    before that sum, and so before the share. Payer and beneficiary of
    the same pair are one counterparty: amounts and payment counts are
    added. Ids outside the directory stay in the sum and are not listed.
    """
    requested = company_id.strip()
    directory_ids = _directory_ids(companies_path)
    if requested not in directory_ids:
        return []

    amounts: dict[str, float] = {}
    counts: dict[str, int] = {}
    company_total = 0.0
    with payments_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            amount = _amount(row.get("PAY_AMT"))
            if amount is None or amount >= _TRILLION_RUB:
                continue
            payer = (row.get("PAYER") or "").strip()
            beneficiary = (row.get("BENEFICIARY") or "").strip()
            if requested not in {payer, beneficiary}:
                continue
            company_total += amount
            other = beneficiary if payer == requested else payer
            if other == requested or other not in directory_ids:
                continue
            amounts[other] = amounts.get(other, 0.0) + amount
            counts[other] = counts.get(other, 0) + _payment_count(row.get("PAY_CNT"))

    if company_total <= 0:
        return []

    selected = [
        CounterpartyShare(
            counterparty_id=other,
            amount_rub=amount,
            payment_count=counts[other],
            share=amount / company_total,
        )
        for other, amount in amounts.items()
        if amount / company_total >= _MIN_SHARE
    ]
    selected.sort(key=lambda item: (-item.share, item.counterparty_id))
    return selected


def _directory_ids(companies_path: Path) -> set[str]:
    """Read the company ids from ``SYNTHETIC_U``. Duplicate rows collapse."""
    found: set[str] = set()
    with companies_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            company_id = (row.get("SYNTHETIC_U") or "").strip()
            if company_id:
                found.add(company_id)
    return found


def _amount(raw: str | None) -> float | None:
    cleaned = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _payment_count(raw: str | None) -> int:
    cleaned = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return 0
    try:
        return int(float(cleaned))
    except ValueError:
        return 0
