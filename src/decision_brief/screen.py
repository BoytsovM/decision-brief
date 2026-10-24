"""Local feed screen: one company, one role, six blocks.

Streamlit stays in ``app``. Ranking, the card, and RSS retention are
plain functions so tests do not open a browser or the network.
"""

from __future__ import annotations

import html
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from decision_brief.bank_cards import position_text
from decision_brief.classify import mark_industry
from decision_brief.companies import load_companies, select_demo_companies
from decision_brief.conclusion import ModelClient, model_conclusion
from decision_brief.feeds import (
    FEED_URLS,
    dedupe_by_link,
    fetch_rss,
    parse_rss,
    source_name_for,
)
from decision_brief.industries import base_exposure
from decision_brief.models import CompanyProfile, Factor, NewsItem, ScoredItem
from decision_brief.roles import (
    ROLE_LABEL_RU,
    Role,
    company_consequence,
    rank_for_role,
    score_every_item,
)

# Nominative labels for the selector. Consequence sentences use another case.
_INDUSTRY_RU: dict[str, str] = {
    "fuel": "нефтегаз",
    "metals": "металлургия",
    "agri": "агропром",
    "housing": "жилищное строительство",
    "infrastructure": "инфраструктурное строительство",
    "real_estate": "недвижимость",
    "auto": "автопром",
    "retail": "розница",
    "horeca": "общепит",
    "transport": "грузоперевозки",
    "energy": "энергетика",
    "it": "ИТ",
    "finance": "финансы",
    "machinery": "машиностроение",
    "chemicals": "химия",
    "wholesale": "оптовая торговля",
    "services": "услуги",
}

# Column names from df_Uid_data_hack.csv. The gloss is for the screen only.
_FIELD_GLOSS: dict[str, str] = {
    "CL_PRODUCT_LOA_MARK": "кредит",
    "CL_PRODUCT_LEA_MARK": "лизинг",
    "FACTORING_MARK": "факторинг",
    "CL_PRODUCT_DEP_MARK": "депозит",
    "ECO_MARK_LABEL": "стремительный рост",
    "FTS_FLAG": "внешнеэкономическая деятельность",
    "OKFS_NAME": "иностранный собственник",
    "CL_PRODUCT_ZPP_MARK": "зарплатный проект",
    "AMOUNT_WORKERS_FNS_GRADATION": "штат",
    "CL_PRODUCT_GAR_MARK": "гарантия",
    "FTS_COUNTRY_NAME": "страна торговли",
}

_COMPANIES_NAME = "df_Uid_data_hack.csv"
_MARKUP = re.compile(r"(?is)<!--.*?-->|<[^>]+>")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class NewsLoad:
    """One RSS attempt.

    ``failed`` is true when no item was read and at least one address
    raised. A valid feed with zero items is not a failure.
    """

    items: tuple[NewsItem, ...]
    failed: bool


@dataclass(frozen=True)
class CardView:
    """Six blocks of one shown item, plus the CSV columns that raised it."""

    happened: str
    why: str
    consequences: str
    bank: str
    model: str
    source_name: str
    source_url: str
    csv_fields: tuple[str, ...]
    score: float
    relevance: str

    def score_line(self) -> str:
        """Russian score and relevance."""
        rendered = f"{self.score:.2f}".replace(".", ",")
        return f"Скор {rendered}, {self.relevance}"

    def csv_fields_line(self) -> str:
        """Russian line naming the CSV columns that raised this score."""
        if not self.csv_fields:
            return "Поля CSV скор не поднимали."
        parts = [_field_label(name) for name in self.csv_fields]
        return "Поля CSV, которые подняли скор: " + ", ".join(parts)


def default_companies_path() -> Path:
    """Path of the company CSV. The file stays in ``data/raw`` and out of git."""
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "raw" / _COMPANIES_NAME


def sample_companies_path() -> Path:
    """Committed synthetic company file. It is not the full hackathon CSV."""
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "sample" / "companies.csv"


def resolve_companies_path(
    environ: Mapping[str, str] | None = None,
    *,
    raw: Path | None = None,
    sample: Path | None = None,
) -> Path:
    """Choose the company CSV without changing ``load_companies``.

    ``DECISION_BRIEF_COMPANIES`` wins when it is set. Otherwise the raw
    file is used when it exists on disk. A checkout without that file
    uses the committed sample. Scoring does not read this path.
    """
    source = os.environ if environ is None else environ
    override = source.get("DECISION_BRIEF_COMPANIES", "").strip()
    if override:
        return Path(override)
    raw_path = default_companies_path() if raw is None else raw
    if raw_path.is_file():
        return raw_path
    if sample is None:
        return sample_companies_path()
    return sample


def companies_source_label(path: Path) -> str:
    """Russian caption for which company file the screen opened."""
    resolved = path.resolve()
    if resolved == default_companies_path().resolve():
        return "Полный файл data/raw/df_Uid_data_hack.csv. В git его нет."
    if resolved == sample_companies_path().resolve():
        return (
            "Синтетический файл data/sample/companies.csv. "
            "Полный CSV не подключён."
        )
    return f"Файл компаний: {path}"


def load_demo_companies(path: Path) -> list[CompanyProfile]:
    """Chat-1 demo set: a company's own revenue is above 15 billion rubles.

    ``load_companies`` is unchanged. ``U_428697`` stays out via ``select_demo_companies``.
    """
    return select_demo_companies(load_companies(path))


def company_label(company: CompanyProfile) -> str:
    """Short Russian label for the company selector."""
    industry = _INDUSTRY_RU.get(company.industry, company.industry)
    details = [industry]
    if company.okved:
        details.append(f"ОКВЭД {company.okved}")
    if company.revenue_rub is not None:
        details.append(_billions(company.revenue_rub))
    return f"{company.synthetic_u} — {', '.join(details)}"


def company_labels(
    companies: Sequence[CompanyProfile],
) -> tuple[tuple[str, CompanyProfile], ...]:
    """Unique selector labels in the same order as ``companies``."""
    seen: dict[str, int] = {}
    rows: list[tuple[str, CompanyProfile]] = []
    for company in companies:
        base = company_label(company)
        seen[base] = seen.get(base, 0) + 1
        label = base if seen[base] == 1 else f"{base} #{seen[base]}"
        rows.append((label, company))
    return tuple(rows)


def role_choices() -> tuple[tuple[str, Role], ...]:
    """Russian role labels in selector order."""
    return tuple((ROLE_LABEL_RU[role], role) for role in Role)


def load_news(
    urls: Sequence[str] = FEED_URLS,
    *,
    fetcher: Callable[[str], str] = fetch_rss,
) -> NewsLoad:
    """Read every address through ``parse_rss``. Feed errors are not raised.

    One broken address does not discard the others. ``failed`` is true
    only when nothing was read and at least one address failed. Scores
    on the items still come from ``factors_in_text`` inside ``parse_rss``.
    """
    collected: list[NewsItem] = []
    failures = 0
    for url in urls:
        try:
            xml_text = fetcher(url)
            collected.extend(parse_rss(xml_text, source_name_for(url)))
        except Exception:
            failures += 1
    unique = dedupe_by_link(collected)
    failed = not unique and failures > 0
    return NewsLoad(tuple(unique), failed)


def retain_feed(
    previous: Sequence[NewsItem],
    loaded: NewsLoad,
) -> tuple[list[NewsItem], bool]:
    """Keep an already computed feed when the new RSS load failed.

    The flag is true when the screen should say that the load failed.
    A successful load replaces the previous feed, including a parsed
    feed that contained no items.
    """
    if loaded.failed and previous:
        return list(previous), True
    if loaded.failed:
        return [], True
    return list(loaded.items), False


def rss_failure_message(*, kept_previous: bool) -> str:
    """Russian line for a failed RSS load."""
    if kept_previous:
        return "Лента RSS не обновилась. Показана уже посчитанная лента."
    return "Лента RSS не загрузилась."


def empty_feed_message() -> str:
    """Russian line when no item is at or above the show threshold."""
    return "Нет новостей выше порога."


def rank_feed(
    company: CompanyProfile,
    items: Sequence[NewsItem],
    role: Role,
    *,
    as_of: date,
) -> list[ScoredItem]:
    """Order one company feed for one role.

    Items below the show threshold are dropped. An industry mention is
    marked for this company before ranking. A material older than a
    year stays hidden because ``score_item`` scores it at 0.
    """
    marked = [mark_industry(item, company.industry) for item in items]
    return rank_for_role(company, marked, role, as_of=as_of)


def parsed_feed(
    company: CompanyProfile,
    items: Sequence[NewsItem],
    role: Role,
    *,
    as_of: date,
) -> list[ScoredItem]:
    """Score every parsed item for the scrollable screen feed.

    Items below the show threshold stay in the list. ``rank_feed`` still
    drops them for ranking that must hide the tail.
    """
    marked = [mark_industry(item, company.industry) for item in items]
    return score_every_item(company, marked, role, as_of=as_of)


def csv_fields_raising_score(
    company: CompanyProfile,
    item: NewsItem,
) -> tuple[str, ...]:
    """CSV columns that increase exposure for a factor this item hits.

    The bumps follow ``exposure``: each matching flag adds 1, the value
    stops at 3, and payroll plus a large staff are one labor bump.
    A flag whose factor is absent from the item did not raise this score.
    A flag that finds the factor already at 3 did not raise it either.
    """
    levels = base_exposure(company.industry)
    raised: list[str] = []
    for columns, factor in _flag_bumps(company):
        if item.factors.get(factor, 0) <= 0:
            continue
        before = levels[factor]
        after = min(3, before + 1)
        if after <= before:
            continue
        levels[factor] = after
        raised.extend(columns)
    return tuple(raised)


def card_view(
    company: CompanyProfile,
    scored: ScoredItem,
    *,
    role: Role | None,
    client: ModelClient | None,
    shown: Sequence[ScoredItem],
) -> CardView:
    """Six blocks for one shown item.

    The model block stays empty when ``client`` is None. No gateway
    call is made in that case. The bank block is the fresh-card
    citation and is not replaced by the model text.
    """
    model = ""
    if client is not None:
        model = model_conclusion(
            company,
            scored,
            role=role,
            client=client,
            shown=shown,
        )
    return CardView(
        happened=_happened(scored.item),
        why="; ".join(scored.reasons),
        consequences=company_consequence(company, scored.item),
        bank=_bank_text(scored),
        model=model,
        source_name=scored.item.source_name,
        source_url=scored.item.source_url,
        csv_fields=csv_fields_raising_score(company, scored.item),
        score=scored.score,
        relevance=scored.relevance.value,
    )


def card_blocks(view: CardView) -> tuple[tuple[str, str], ...]:
    """Six blocks in screen order. The model body may be empty."""
    return (
        ("Что произошло", view.happened),
        ("Почему этой компании", view.why),
        ("Последствия", view.consequences),
        ("Как оценивает банк", view.bank),
        ("Вывод модели", view.model),
        ("Источник", view.source_url),
    )


def source_link_html(name: str, url: str) -> str:
    """HTML for the source line. Only an http(s) URL becomes a link."""
    cleaned = url.strip()
    label = html.escape(name.strip() or cleaned)
    if cleaned.startswith(("http://", "https://")):
        href = html.escape(cleaned, quote=True)
        return (
            f'<a href="{href}" target="_blank" '
            f'rel="noopener noreferrer">{label}</a>'
        )
    return html.escape(f"{name} {cleaned}".strip())


def markdown_block(text: str) -> str:
    """Markdown that shows ``text`` as plain sentences, including line breaks."""
    escaped = text.replace("\\", "\\\\")
    for char in ("*", "_", "`", "[", "]"):
        escaped = escaped.replace(char, "\\" + char)
    return escaped.replace("\n", "  \n")


def _field_label(name: str) -> str:
    gloss = _FIELD_GLOSS.get(name)
    if gloss is None:
        return name
    return f"{name} ({gloss})"


def _billions(revenue_rub: float) -> str:
    rendered = f"{revenue_rub / 1_000_000_000:.1f}".replace(".", ",")
    return f"{rendered} млрд руб."


def _happened(item: NewsItem) -> str:
    """Title plus summary, without RSS markup such as an HTML comment."""
    title = _plain_news(item.title)
    summary = _plain_news(item.summary)
    if not title:
        return summary
    if not summary or summary == title:
        return title
    return f"{title} {summary}"


def _plain_news(text: str) -> str:
    cleaned = html.unescape(_MARKUP.sub(" ", text))
    return _SPACE.sub(" ", cleaned).strip()


def _bank_text(scored: ScoredItem) -> str:
    card = scored.bank_card
    if card is None or not card.fresh:
        return "Свежей карточки банка по этому фактору нет."
    return position_text(card, scored.item)


def _flag_bumps(
    company: CompanyProfile,
) -> tuple[tuple[tuple[str, ...], Factor], ...]:
    """Flags in the same order ``exposure`` applies them."""
    rows: list[tuple[tuple[str, ...], Factor]] = []
    singles: tuple[tuple[str, tuple[str, ...], Factor], ...] = (
        ("has_loan", ("CL_PRODUCT_LOA_MARK",), Factor.RATE),
        ("has_leasing", ("CL_PRODUCT_LEA_MARK",), Factor.RATE),
        ("has_factoring", ("FACTORING_MARK",), Factor.RATE),
        ("has_deposit", ("CL_PRODUCT_DEP_MARK",), Factor.RATE),
        ("rapid_growth", ("ECO_MARK_LABEL",), Factor.RATE),
        ("has_foreign_trade", ("FTS_FLAG",), Factor.FX),
        ("foreign_owner", ("OKFS_NAME",), Factor.FX),
    )
    for attr, columns, factor in singles:
        if getattr(company, attr):
            rows.append((columns, factor))
    labor: list[str] = []
    if company.has_payroll:
        labor.append("CL_PRODUCT_ZPP_MARK")
    if company.staff_over_100:
        labor.append("AMOUNT_WORKERS_FNS_GRADATION")
    if labor:
        rows.append((tuple(labor), Factor.LABOR))
    if company.has_guarantee:
        rows.append((("CL_PRODUCT_GAR_MARK",), Factor.BUDGET))
    country = company.foreign_trade_countries.casefold()
    if "китай" in country and company.industry in {"metals", "fuel", "agri"}:
        rows.append((("FTS_COUNTRY_NAME",), Factor.COMMODITY))
    return tuple(rows)
