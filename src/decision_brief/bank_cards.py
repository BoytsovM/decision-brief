"""Short Alfa-Bank notes. Full PDF text is not stored here.

Quotations keep an empty page when the PDF page was not recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from decision_brief.models import BankCard, BankThesis, Factor, NewsItem

BANK_CARDS: tuple[BankCard, ...] = (
    BankCard(
        card_id="K1",
        title="Инфляция 25–31 августа",
        published_on=date(2026, 9, 2),
        filename="Inflation_tracker_02.pdf",
        summary=(
            "Недельная дефляция 0,01% при росте цен на бензин. "
            "Новая волна роста цен на топливо не исчерпана."
        ),
        factors=(Factor.INFLATION, Factor.FUEL),
        theses=(
            BankThesis(
                text=(
                    "Недельная дефляция 0,01% при росте цен на бензин. "
                    "Новая волна роста цен на топливо не исчерпана."
                ),
                factor=Factor.INFLATION,
            ),
        ),
    ),
    BankCard(
        card_id="K2",
        title="Ключевая ставка осталась 14,0%",
        published_on=date(2026, 9, 11),
        filename="ALFA-Macro_Insights-Policy_Rate_11Sep.pdf",
        summary=(
            "11 сентября 2026 года ЦБ оставил ставку 14,0%. "
            "Снижение не рассматривалось. Прогноз: 14,0% на конец 2026 "
            "и 12,0% на конец 2027. Курс к концу 2026: 87,2 руб./$."
        ),
        factors=(Factor.RATE, Factor.FX, Factor.INFLATION),
        theses=(
            BankThesis(
                text=(
                    "Ставка: 14,0%, пауза 23 октября, "
                    "14,0% на конец 2026 и 12,0% на конец 2027."
                ),
                factor=Factor.RATE,
            ),
            BankThesis(
                text="Инфляция 2026: 7,5%.",
                factor=Factor.INFLATION,
            ),
            BankThesis(
                text="Курс на конец 2026: 87,2 руб./$.",
                factor=Factor.FX,
            ),
        ),
    ),
    BankCard(
        card_id="K3",
        title="Макростатистика 7 месяцев 2026",
        published_on=date(2026, 9, 7),
        filename="ALFA-7M26.pdf",
        summary="Рынок труда жёсткий, зарплаты растут быстрее ожиданий.",
        factors=(Factor.LABOR,),
        theses=(
            BankThesis(
                text="Рынок труда жёсткий.",
                factor=Factor.LABOR,
            ),
        ),
    ),
    BankCard(
        card_id="K4",
        title="Потребление на пике",
        published_on=date(2026, 8, 5),
        filename="ALFA-consumption.pdf",
        summary="Потребление на пике, в 4 квартале 2026 рост около нуля.",
        factors=(Factor.DEMAND,),
        theses=(
            BankThesis(
                text="Потребление в 4 квартале 2026 около нуля.",
                factor=Factor.DEMAND,
            ),
        ),
    ),
    BankCard(
        card_id="K5",
        title="Макростатистика 1 полугодия 2026",
        published_on=date(2026, 7, 31),
        filename="ALFA-macro_stat1H26.pdf",
        summary="ВВП за 1 полугодие вырос на 0,3%, прогноз на 2026 снижен до 0,1%.",
        factors=(Factor.DEMAND, Factor.BUDGET),
        theses=(
            BankThesis(
                text="ВВП 2026: +0,1%.",
                factor=Factor.DEMAND,
            ),
        ),
    ),
    BankCard(
        card_id="K6",
        title="Российская сталь, 1 квартал 2021",
        published_on=date(2021, 4, 15),
        filename="ALFA_Russian_Steels_1K21.pdf",
        summary="Исторический материал 2021 года. Как текущую позицию банка не использовать.",
        factors=(Factor.COMMODITY,),
        fresh=False,
        theses=(
            BankThesis(
                text=(
                    "Исторический материал 2021 года. "
                    "Как текущую позицию банка не использовать."
                ),
                factor=Factor.COMMODITY,
            ),
        ),
    ),
    # K7 also mentioned a 14.25% rate path. That path is stale and is not stored.
    BankCard(
        card_id="K7",
        title="Тактический взгляд на 3 квартал 2026",
        published_on=date(2026, 7, 22),
        filename="FI_Strategy_3Q26_22072026.pdf",
        summary="67% кредитов юрлицам выданы по плавающей ставке, процентный риск на заёмщике.",
        factors=(Factor.DEBT, Factor.RATE),
        theses=(
            BankThesis(
                text="67% кредитов юрлицам по плавающей ставке.",
                factor=Factor.DEBT,
            ),
        ),
    ),
    BankCard(
        card_id="K8",
        title="Бонд-бриф",
        published_on=date(2026, 9, 14),
        filename="Бонд_Бриф_14092026.pdf",
        summary="После паузы ЦБ доходности ОФЗ выросли. Ближайших драйверов для улучшения рынка нет.",
        factors=(Factor.DEBT, Factor.RATE),
        theses=(
            BankThesis(
                text=(
                    "После паузы ЦБ доходности ОФЗ выросли. "
                    "Ближайших драйверов для улучшения рынка нет."
                ),
                factor=Factor.DEBT,
            ),
        ),
    ),
    BankCard(
        card_id="K9",
        title="Обзор рынка золота, август 2026",
        published_on=date(2026, 9, 7),
        filename="Gold_digest_August26.pdf",
        summary="Золото выросло за август на 9,7%, жёсткий сигнал ФРС охладил ралли.",
        factors=(Factor.COMMODITY,),
        theses=(
            BankThesis(
                text="Золото выросло за август на 9,7%, жёсткий сигнал ФРС охладил ралли.",
                factor=Factor.COMMODITY,
            ),
        ),
    ),
)

_FACTOR_LABEL: dict[Factor, str] = {
    Factor.RATE: "ставка",
    Factor.FX: "курс",
    Factor.INFLATION: "инфляция",
    Factor.DEMAND: "спрос",
    Factor.LABOR: "рынок труда",
    Factor.FUEL: "топливо",
    Factor.BUDGET: "бюджет",
    Factor.DEBT: "долг",
    Factor.COMMODITY: "сырьё",
}


@dataclass(frozen=True)
class CitedThesis:
    """One sentence plus the card fields required to quote it.

    ``page`` is empty when the PDF page is not known.
    """

    card_id: str
    filename: str
    published_on: date
    factor: Factor
    fresh: bool
    text: str
    page: str


def fresh_cards() -> tuple[BankCard, ...]:
    """Return bank notes that are still a current position."""
    return tuple(card for card in BANK_CARDS if card.fresh)


def latest_card_for(factor: Factor) -> BankCard | None:
    """Pick the newest fresh card whose main topic is the factor.

    A card can mention several factors. The rate decision stays K2 even
    though a later bond brief also mentions the rate.
    """
    matches = [card for card in fresh_cards() if factor in card.factors]
    if not matches:
        return None
    primary = [card for card in matches if card.factors[0] is factor]
    pool = primary or matches
    return max(pool, key=lambda card: card.published_on)


def cited_theses(card: BankCard) -> tuple[CitedThesis, ...]:
    """Copy id, file, date, freshness, and page onto each sentence."""
    return tuple(
        CitedThesis(
            card_id=card.card_id,
            filename=card.filename,
            published_on=card.published_on,
            factor=thesis.factor,
            fresh=card.fresh,
            text=thesis.text,
            page=card.page,
        )
        for thesis in card.theses
    )


def current_citations() -> tuple[CitedThesis, ...]:
    """Quotations that still belong to the current bank position.

    A card with ``fresh`` false, including the 2021 steel note, is left out.
    """
    rows: list[CitedThesis] = []
    for card in fresh_cards():
        rows.extend(cited_theses(card))
    return tuple(rows)


def cards_missing_page() -> tuple[str, ...]:
    """Return card ids whose PDF page was not recorded.

    An empty string is a gap. It is not page zero and must not be filled
    with a guessed number.
    """
    return tuple(card.card_id for card in BANK_CARDS if card.page == "")


def format_citation(cited: CitedThesis) -> str:
    """Return one Russian line. An unknown page stays blank after «стр.»."""
    freshness = "актуально" if cited.fresh else "неактуально"
    page = f"стр. {cited.page}".rstrip()
    published = cited.published_on.strftime("%d.%m.%Y")
    label = _FACTOR_LABEL[cited.factor]
    return (
        f"{cited.card_id}, {cited.filename}, {published}, "
        f"{label}, {freshness}, {page}: «{cited.text}»"
    )


def position_text(card: BankCard | None, item: NewsItem) -> str:
    """Russian citations for the bank block of one news item.

    The thesis that matches the news factor is placed first. Other
    sentences of the same card follow, each with its own factor. The
    PDF page is left blank when the card has none. No model call.
    """
    if card is None:
        return "Свежей карточки банка по этому фактору нет."
    rows = _ordered_for_item(card, item)
    if not rows:
        return f"{card.card_id}, {card.published_on.isoformat()}: {card.summary}"
    return "\n".join(format_citation(row) for row in rows)


def _ordered_for_item(card: BankCard, item: NewsItem) -> tuple[CitedThesis, ...]:
    rows = list(cited_theses(card))
    top = _leading_factor(item)
    if top is None:
        return tuple(rows)
    matched = [row for row in rows if row.factor is top]
    if not matched:
        return tuple(rows)
    rest = [row for row in rows if row.factor is not top]
    return tuple(matched + rest)


def _leading_factor(item: NewsItem) -> Factor | None:
    if not item.factors:
        return None
    top = max(item.factors, key=item.factors.get)
    if isinstance(top, Factor):
        return top
    return None
