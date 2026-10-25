"""Short Alfa-Bank notes. Full PDF text is not stored here.

Paraphrases carry visually verified page references; original PDFs stay external.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
                    "Ставка: 14,0%. Банк ожидает паузу 23 октября, "
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
        summary="Данные рынка труда не подтверждают охлаждения экономики; рост зарплат остаётся высоким.",
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
                text="Прогноз роста потребления в 4 квартале 2026 около нуля.",
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

# Verified against the case's public source folder on 2026-10-22.
# K6 is historical and intentionally excluded. K9's exact publication day is unknown.
_PROVENANCE = {
    "K1": ("1", "19iW3Ph8_wO0HHQY7Ik4lTfC3jRc9gjWV"),
    "K2": ("1-2", "1shHG89LtMgHT1_uEebHmQSFZe_zbeq7-"),
    "K3": ("1", "1HZDq3WGRFdzgm1TZ5hWL23Q3I9c2Eq64"),
    "K4": ("1", "1riR1lhsb6EY1MwGMxdBlS_tI5ed9mIiz"),
    "K5": ("1", "1khcHwoS0FkG9p_0J4XoHGaGq3B4V0ime"),
    "K6": ("", "1yLCBrIoyIsubLTEBvBHh6io48ysnW-wn"),
    "K7": ("10", "1hq3Fhyz9ce_sRyGUQB1MdoHeQdfAJfhK"),
    "K8": ("1", "1bPzix_332N2CyMY0tqCHuYtGsfJWnFGv"),
    "K9": ("2-3", "1a7TXOCHARfKzUR0hn9Cm9gQSrIldxTDE"),
}


BANK_CARDS = tuple(replace(card, page=_PROVENANCE[card.card_id][0],
    source_url=f"https://drive.google.com/file/d/{_PROVENANCE[card.card_id][1]}/view",
    source_note=("Отчёт за август 2026; точный день публикации не подтверждён. "
                 "Дата индекса 07.09.2026 сохранена из исходной версии."
                 if card.card_id == "K9" else "")) for card in BANK_CARDS)

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
        f"{label}, {freshness}, {page}; пересказ: {cited.text}"
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
