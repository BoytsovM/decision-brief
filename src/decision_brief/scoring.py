"""Company filter that runs before any language model call."""

from __future__ import annotations

from datetime import date

from decision_brief.industries import base_exposure
from decision_brief.models import CompanyProfile, Factor, NewsItem, Relevance

_STALE_AFTER_DAYS = 365
_IMPORTANT_AT = 0.6
_NOTICE_AT = 0.3
_INDUSTRY_MENTION_BONUS = 0.15


def exposure(company: CompanyProfile) -> dict[Factor, int]:
    """Combine the industry baseline with CSV flags. Each factor stays in 0..3.

    A missing product flag does not reduce exposure. Flags only add.
    The numeric bonus is +1 per matching flag until the spreadsheet
    replaces these weights.
    """
    scores = base_exposure(company.industry)
    bumps: list[tuple[bool, Factor]] = [
        (company.has_loan, Factor.RATE),
        (company.has_leasing, Factor.RATE),
        (company.has_factoring, Factor.RATE),
        (company.has_deposit, Factor.RATE),
        (company.rapid_growth, Factor.RATE),
        (company.has_foreign_trade, Factor.FX),
        (company.foreign_owner, Factor.FX),
        (company.has_payroll or company.staff_over_100, Factor.LABOR),
        (company.has_guarantee, Factor.BUDGET),
    ]
    country = company.foreign_trade_countries.upper()
    if "КИТАЙ" in country and company.industry in {"metals", "fuel", "agri"}:
        bumps.append((True, Factor.COMMODITY))
    for enabled, factor in bumps:
        if enabled:
            scores[factor] = min(3, scores[factor] + 1)
    return scores


def _contribution(strength: int, factor_exposure: int) -> float:
    """One factor's weight in the noisy-OR. Both axes are 0..3."""
    clamped_strength = min(3, max(0, strength))
    clamped_exposure = min(3, max(0, factor_exposure))
    return (clamped_strength / 3) * (clamped_exposure / 3) * 0.8


def score_item(
    company: CompanyProfile,
    item: NewsItem,
    *,
    as_of: date,
) -> tuple[float, tuple[str, ...]]:
    """Return a 0..1 score and the Russian reasons that produced it.

    Materials older than a year score 0. Strength and exposure are both
    divided by 3 so one factor cannot exceed 1.
    """
    age_days = (as_of - item.published_on).days
    if age_days < 0:
        return 0.0, ("Дата публикации в будущем; событие требует проверки.",)
    if age_days > _STALE_AFTER_DAYS:
        return 0.0, ("Материал старше года, в ленту не берём.",)
    company_exposure = exposure(company)
    survival = 1.0
    reasons: list[str] = []
    for factor, strength in item.factors.items():
        if strength <= 0:
            continue
        weight = _contribution(strength, company_exposure[factor])
        if weight <= 0:
            continue
        survival *= 1 - weight
        reasons.append(
            f"{factor.name}: сила {strength}, экспозиция {company_exposure[factor]}"
        )
    value = 1 - survival
    if item.mentions_industry:
        value += _INDUSTRY_MENTION_BONUS
        reasons.append("Новость прямо называет отрасль компании.")
    value = min(1.0, value) * item.coverage
    if not reasons:
        reasons.append("Ни один фактор новости не совпал с профилем компании.")
    return value, tuple(reasons)


def relevance_for(score: float) -> Relevance:
    """Map a score to the three labels from the team note."""
    if score >= _IMPORTANT_AT:
        return Relevance.IMPORTANT
    if score >= _NOTICE_AT:
        return Relevance.NOTICE
    return Relevance.HIDDEN
