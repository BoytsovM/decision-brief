"""Load company rows and group rollups from the hackathon CSV.

The full file stays out of git. A company's own revenue and its group's
revenue sum are separate tests.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from decision_brief.industries import industry_for_okved, normalize_okved
from decision_brief.models import CompanyProfile

_LARGE_REVENUE_RUB = 15_000_000_000
_EXCLUDED_DEMO_ID = "U_428697"


@dataclass(frozen=True)
class GroupSummary:
    """Revenue and size of one GROUP_ID.

    ``passes_large_revenue`` compares the group sum with 15 billion rubles.
    It does not say that any single member belongs in the demo set.
    """

    group_id: str
    revenue_rub: float
    legal_entity_count: int
    passes_large_revenue: bool


def load_companies(csv_path: Path) -> list[CompanyProfile]:
    """Read the semicolon-separated company file."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        return [_row_to_profile(row) for row in reader]


def is_demo_candidate(company: CompanyProfile) -> bool:
    """Keep companies that themselves clear the case revenue threshold."""
    if company.revenue_rub is None:
        return False
    return company.revenue_rub >= _LARGE_REVENUE_RUB


def in_demo_set(company: CompanyProfile) -> bool:
    """True when this legal entity belongs in the demo set.

    The gate is the company's own revenue. ``U_428697`` is a repeated
    synthetic id and is left out even when that revenue is large.
    """
    if company.synthetic_u == _EXCLUDED_DEMO_ID:
        return False
    return is_demo_candidate(company)


def select_demo_companies(companies: list[CompanyProfile]) -> list[CompanyProfile]:
    """Return the demo set, in the same order as ``companies``."""
    return [company for company in companies if in_demo_set(company)]


def summarize_groups(csv_path: Path) -> list[GroupSummary]:
    """Sum revenue and count legal-entity rows for each GROUP_ID.

    A group is large when the sum of ``REVENUE_COMPANY`` reaches
    15 billion rubles. That flag is not the demo-set test. Rows with
    an empty ``GROUP_ID`` are skipped. A missing revenue adds nothing.
    """
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            group_id = (row.get("GROUP_ID") or "").strip()
            if not group_id:
                continue
            revenue = _float_or_none(row.get("REVENUE_COMPANY"))
            totals[group_id] += revenue or 0.0
            counts[group_id] += 1
    summaries = [
        GroupSummary(
            group_id=group_id,
            revenue_rub=totals[group_id],
            legal_entity_count=counts[group_id],
            passes_large_revenue=totals[group_id] >= _LARGE_REVENUE_RUB,
        )
        for group_id in totals
    ]
    summaries.sort(key=lambda item: item.group_id)
    return summaries


def _row_to_profile(row: dict[str, str]) -> CompanyProfile:
    okved = normalize_okved(row.get("MAINOKVED_CODE") or "")
    staff = (row.get("AMOUNT_WORKERS_FNS_GRADATION") or "").casefold()
    eco = (row.get("ECO_MARK_LABEL") or "").casefold()
    return CompanyProfile(
        synthetic_u=(row.get("SYNTHETIC_U") or "").strip(),
        industry=industry_for_okved(okved),
        okved=okved,
        revenue_rub=_float_or_none(row.get("REVENUE_COMPANY")),
        has_loan=_marked(row.get("CL_PRODUCT_LOA_MARK")),
        has_leasing=_marked(row.get("CL_PRODUCT_LEA_MARK")),
        has_factoring=_marked(row.get("FACTORING_MARK")),
        has_guarantee=_marked(row.get("CL_PRODUCT_GAR_MARK")),
        has_deposit=_marked(row.get("CL_PRODUCT_DEP_MARK")),
        has_payroll=_marked(row.get("CL_PRODUCT_ZPP_MARK")),
        has_foreign_trade=_marked(row.get("FTS_FLAG")),
        foreign_trade_countries=(row.get("FTS_COUNTRY_NAME") or "").strip(),
        foreign_owner="иностран" in (row.get("OKFS_NAME") or "").casefold(),
        staff_over_100=any(token in staff for token in ("101", "251", "500")),
        rapid_growth="стремительн" in eco,
    )


def _marked(raw: str | None) -> bool:
    return (raw or "").strip() in {"1", "1.0", "да", "true", "True"}


def _float_or_none(raw: str | None) -> float | None:
    cleaned = (raw or "").strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None
