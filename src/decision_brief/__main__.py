"""Print two briefs for the same rate headline."""

from __future__ import annotations

from datetime import date

from decision_brief.classify import factors_in_text
from decision_brief.conclusion import brief_card
from decision_brief.models import CompanyProfile, NewsItem
from decision_brief.pipeline import rank_for_company

_AS_OF = date(2026, 10, 21)


def demo_companies() -> tuple[CompanyProfile, CompanyProfile]:
    """Two profiles that must not get the same brief."""
    carrier = CompanyProfile(
        synthetic_u="U_3263",
        industry="transport",
        okved="49.41.2",
        revenue_rub=32_300_000_000,
        has_leasing=True,
        staff_over_100=True,
    )
    restaurant = CompanyProfile(
        synthetic_u="demo-horeca",
        industry="horeca",
        okved="56.10",
        revenue_rub=20_000_000_000,
    )
    return carrier, restaurant


def main() -> None:
    """Score one rate item for a carrier and a restaurant."""
    title = "ЦБ сохранил ключевую ставку 14,0%"
    summary = "11 сентября 2026 года ставка осталась 14,0%."
    item = NewsItem(
        title=title,
        published_on=date(2026, 9, 11),
        source_name="Альфа-Банк",
        source_url="bank://K2",
        summary=summary,
        factors=factors_in_text(f"{title} {summary}"),
    )
    for company in demo_companies():
        ranked = rank_for_company(company, [item], as_of=_AS_OF)
        if not ranked:
            print(f"{company.synthetic_u}: новость скрыта\n")
            continue
        print(brief_card(company, ranked[0], shown=ranked))
        print()


if __name__ == "__main__":
    main()
