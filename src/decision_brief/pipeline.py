"""Rank news for one company and attach the newest bank note."""

from __future__ import annotations

from datetime import date

from decision_brief.bank_cards import latest_card_for, position_text
from decision_brief.classify import payment_ruble
from decision_brief.models import (
    CompanyProfile,
    Factor,
    NewsItem,
    Relevance,
    ScoredItem,
)
from decision_brief.roles import ROLE_LABEL_RU, Role, company_consequence
from decision_brief.scoring import relevance_for, score_item


def rank_for_company(
    company: CompanyProfile,
    items: list[NewsItem],
    *,
    as_of: date,
) -> list[ScoredItem]:
    """Score every item and drop those below the show threshold."""
    scored: list[ScoredItem] = []
    for item in items:
        value, reasons = score_item(company, item, as_of=as_of)
        label = relevance_for(value)
        if label is Relevance.HIDDEN:
            continue
        scored.append(
            ScoredItem(
                item=item,
                score=value,
                relevance=label,
                reasons=reasons,
                bank_card=_bank_card_for(item),
            )
        )
    scored.sort(key=lambda row: row.score, reverse=True)
    return scored


def explain(company: CompanyProfile, scored: ScoredItem) -> str:
    """Build the six-block card from rules and a bank note. No model call.

    Consequences come from the item's factors and this profile. The
    model block stays empty. A bank card is quoted only when it is fresh.
    """
    return "\n".join(
        (
            f"Компания {company.synthetic_u} ({company.industry}), "
            f"скор {scored.score:.2f}, {scored.relevance.value}",
            f"Что произошло. {scored.item.title}",
            f"Почему этой компании. {'; '.join(scored.reasons)}",
            f"Последствия. {company_consequence(company, scored.item)}",
            f"Как оценивает банк. {_fresh_bank_text(scored)}",
            "Вывод модели.",
            f"Источник новости. {scored.item.source_url}",
        )
    )


def explain_for_role(
    company: CompanyProfile,
    scored: ScoredItem,
    role: Role,
) -> str:
    """Same six blocks as ``explain``, with the person's role on the first line.

    The model block stays empty. No model call.
    """
    text = explain(company, scored)
    first, separator, rest = text.partition("\n")
    label = ROLE_LABEL_RU[role]
    return f"{first}, роль {label}{separator}{rest}"


def _fresh_bank_text(scored: ScoredItem) -> str:
    card = scored.bank_card
    if card is None or not card.fresh:
        return "Свежей карточки банка по этому фактору нет."
    return position_text(card, scored.item)


def _bank_card_for(item: NewsItem):
    if payment_ruble(f"{item.title} {item.summary}"):
        return None
    if not item.factors:
        return None
    top = max(item.factors, key=item.factors.get)
    return latest_card_for(top if isinstance(top, Factor) else Factor.RATE)
