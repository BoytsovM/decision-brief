"""Shared records passed between the feed, the filter, and the card."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Factor(Enum):
    """Macro factor a news item can hit."""

    RATE = "F1"
    FX = "F2"
    INFLATION = "F3"
    DEMAND = "F4"
    LABOR = "F5"
    FUEL = "F6"
    BUDGET = "F7"
    DEBT = "F8"
    COMMODITY = "F9"


class Relevance(Enum):
    """How a scored item is shown."""

    IMPORTANT = "важно"
    NOTICE = "к сведению"
    HIDDEN = "не показывать"


@dataclass(frozen=True)
class CompanyProfile:
    """One legal entity, or the features we know about it."""

    synthetic_u: str
    industry: str
    okved: str = ""
    revenue_rub: float | None = None
    has_loan: bool = False
    has_leasing: bool = False
    has_factoring: bool = False
    has_guarantee: bool = False
    has_deposit: bool = False
    has_payroll: bool = False
    has_foreign_trade: bool = False
    foreign_trade_countries: str = ""
    foreign_owner: bool = False
    staff_over_100: bool = False
    rapid_growth: bool = False


@dataclass(frozen=True)
class NewsItem:
    """One external article or one bank note."""

    title: str
    published_on: date
    source_name: str
    source_url: str
    summary: str = ""
    factors: dict[Factor, int] = field(default_factory=dict)
    mentions_industry: bool = False
    coverage: float = 1.0


@dataclass(frozen=True)
class BankThesis:
    """One sentence stored so it can be shown verbatim later."""

    text: str
    factor: Factor


@dataclass(frozen=True)
class BankCard:
    """Short expert note extracted from one Alfa-Bank PDF.

    ``theses`` are the sentences that may be quoted. The id, file, date,
    and freshness stay on the card. ``page`` is the PDF page; it stays
    empty when that page was not recorded.
    """

    card_id: str
    title: str
    published_on: date
    filename: str
    summary: str
    factors: tuple[Factor, ...]
    fresh: bool = True
    page: str = ""
    theses: tuple[BankThesis, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScoredItem:
    """News item after the company filter."""

    item: NewsItem
    score: float
    relevance: Relevance
    reasons: tuple[str, ...]
    bank_card: BankCard | None
