"""Assign macro factors to a headline without calling a model."""

from __future__ import annotations

import re
from dataclasses import dataclass

from decision_brief.models import Factor, NewsItem

_KEYWORDS: tuple[tuple[Factor, tuple[str, ...]], ...] = (
    (Factor.RATE, ("ставк", "ключев")),
    (Factor.FX, ("курс", "рубл", "доллар", "юан")),
    (Factor.INFLATION, ("инфляц", "дефляц")),
    (Factor.DEMAND, ("потреблен", "спрос")),
    (Factor.LABOR, ("зарплат", "безработ", "кадр")),
    (Factor.FUEL, ("бензин", "дизел", "топлив", "нефт")),
    (Factor.BUDGET, ("бюджет", "госзаказ", "госконтракт")),
    (Factor.DEBT, ("офз", "облигац", "долгов")),
    (Factor.COMMODITY, ("золот", "сталь", "металл")),
)


_DIGITAL_RUBLE = re.compile(r"цифров\w*\s+рубл\w*", re.IGNORECASE)
_MONEY_RUBLE = re.compile(
    r"\d[\d\s\u00a0,.]*\s*(?:млрд|млн|трлн|тыс\.?)?\s*рубл\w*",
    re.IGNORECASE,
)
_HOUSEHOLD_MORTGAGE = re.compile(
    r"семейн\w*\s+ипотек\w*|ипотек\w*\s+семейн\w*",
    re.IGNORECASE,
)


def payment_ruble(text: str) -> bool:
    """True when «рубль» names the digital payment instrument, not a rate."""
    return _DIGITAL_RUBLE.search(text) is not None


def household_mortgage(text: str) -> bool:
    """True when the headline is about a household family mortgage.

    A mention only in the body does not make the article that product.
    Pass the headline, or a headline and a body separated by a newline.
    """
    headline = text.split("\n", 1)[0]
    return _HOUSEHOLD_MORTGAGE.search(headline) is not None


def _scan_text(text: str) -> str:
    """Remove ruble phrases that are not an exchange rate.

    A digital ruble and a sum in rubles must not become a currency factor.
    «Курс рубля» stays, because the rate word is still in the text.
    """
    without_instrument = _DIGITAL_RUBLE.sub(" ", text)
    return _MONEY_RUBLE.sub(" ", without_instrument)


def factors_in_text(text: str) -> dict[Factor, int]:
    """Return factor strengths 0..3 found in a title or summary.

    A direct hit is strength 3. Several keyword groups can fire at once.
    """
    folded = _scan_text(text).casefold()
    found: dict[Factor, int] = {}
    for factor, needles in _KEYWORDS:
        if any(needle in folded for needle in needles):
            found[factor] = 3
    return found


# Credit and deposit are product channels. They are not Factor members:
# the industry matrix is nine columns, and adding a member would break it.
_CREDIT_NEEDLES: tuple[str, ...] = ("кредит", "ипотек", "заём", "заем")
_DEPOSIT_NEEDLES: tuple[str, ...] = ("депозит", "вклад")

# A direct sector name. "Банк России" is the regulator, not the industry.
_INDUSTRY_NAMES: dict[str, tuple[str, ...]] = {
    "fuel": ("нефтегаз", "нефтян", "топливн"),
    "metals": ("металлург", "сталелитей"),
    "agri": ("агропром", "сельск", "аграрн"),
    "housing": ("жилищн", "девелопмент", "строительн", "строительств"),
    "infrastructure": ("инфраструктур",),
    "real_estate": ("недвижим"),
    "auto": ("автопром", "автомобил"),
    "retail": ("розничн", "ритейл"),
    "horeca": ("общепит", "ресторан"),
    "transport": ("транспортн", "грузоперевоз", "логистическ"),
    "energy": ("электроэнерг", "энергетическ"),
    "it": ("ит-отрасл", "it-отрасл", "айти-отрасл"),
    "finance": ("банковский сектор", "банковская отрасл", "финансовый сектор"),
    "machinery": ("машиностроен"),
    "chemicals": ("химпром", "химическ"),
    "wholesale": ("оптов"),
    "services": ("сфера услуг", "сфере услуг"),
}


@dataclass(frozen=True)
class GradedText:
    """Strength 1..3 for macro factors, plus credit and deposit channels.

    ``factors_in_text`` still marks every hit as 3. Zero means the
    channel was not found. ``mentions_industry`` is true only when the
    text names that industry as a sector.
    """

    factors: dict[Factor, int]
    credit: int
    deposit: int
    mentions_industry: bool


def grade_text(title: str, summary: str = "", industry: str = "") -> GradedText:
    """Grade strength from 1 to 3 and note a directly named industry.

    A stem in the title is 3. The same stem only in the summary is 2
    when it occurs at least twice and 1 when it occurs once. Credit and
    deposit use the same scale and stay outside ``Factor``.
    """
    factors: dict[Factor, int] = {}
    for factor, needles in _KEYWORDS:
        strength = _strength(title, summary, needles)
        if strength:
            factors[factor] = strength
    named = _names_industry(f"{title}\n{summary}", industry)
    return GradedText(
        factors=factors,
        credit=_strength(title, summary, _CREDIT_NEEDLES),
        deposit=_strength(title, summary, _DEPOSIT_NEEDLES),
        mentions_industry=named,
    )


def mark_industry(item: NewsItem, industry: str) -> NewsItem:
    """Copy ``item`` with ``mentions_industry`` taken from ``grade_text``.

    Factor strengths already stored on the item are kept. ``parse_rss``
    therefore still exposes the flat scores from ``factors_in_text``.
    """
    graded = grade_text(item.title, item.summary, industry=industry)
    named = graded.mentions_industry
    if item.mentions_industry == named:
        return item
    return NewsItem(
        title=item.title,
        published_on=item.published_on,
        source_name=item.source_name,
        source_url=item.source_url,
        summary=item.summary,
        factors=dict(item.factors),
        mentions_industry=named,
        coverage=item.coverage,
    )


def _strength(title: str, summary: str, needles: tuple[str, ...]) -> int:
    folded_title = _scan_text(title).casefold()
    if any(needle in folded_title for needle in needles):
        return 3
    hits = sum(_scan_text(summary).casefold().count(needle) for needle in needles)
    if hits >= 2:
        return 2
    if hits == 1:
        return 1
    return 0


def _names_industry(text: str, industry: str) -> bool:
    phrases = _INDUSTRY_NAMES.get(industry)
    if not phrases:
        return False
    folded = text.casefold()
    return any(phrase in folded for phrase in phrases)
