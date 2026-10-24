"""JSON for the Figma frontend. Scoring stays in ``parsed_feed``.

The browser does not parse RSS. This module only projects companies,
roles, and already scored items into the fields the screen draws.
The model client is never called here.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from decision_brief.agent import AgentResult
from decision_brief.bank_cards import cited_theses
from decision_brief.models import CompanyProfile, Factor, NewsItem, Relevance, ScoredItem
from decision_brief.roles import ROLE_LABEL_RU, Role, company_consequence
from decision_brief.screen import (
    card_view,
    company_labels,
    csv_fields_raising_score,
    parsed_feed,
)

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

_FACTOR_RU: dict[Factor, str] = {
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

_MONTHS: tuple[str, ...] = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

_MARKUP = re.compile(r"(?is)<!--.*?-->|<[^>]+>")
_SPACE = re.compile(r"\s+")


def plain_text(value: str) -> str:
    """Drop RSS markup and collapse whitespace."""
    cleaned = html.unescape(_MARKUP.sub(" ", value or ""))
    return _SPACE.sub(" ", cleaned).strip()


def list_companies(companies: Sequence[CompanyProfile]) -> list[dict[str, str]]:
    """Selector rows. ``id`` is the synthetic company id."""
    rows: list[dict[str, str]] = []
    for label, company in company_labels(companies):
        if not company.synthetic_u:
            continue
        rows.append({
            "id": company.synthetic_u,
            "label": label,
            "chip": company_chip(company),
        })
    return rows


def list_roles() -> list[dict[str, str]]:
    """Role selector in ``Role`` order, with a capitalised Russian label."""
    rows: list[dict[str, str]] = []
    for role in Role:
        label = ROLE_LABEL_RU[role]
        rows.append({"id": role.value, "label": label[:1].upper() + label[1:]})
    return rows


def company_chip(company: CompanyProfile) -> str:
    """Short header label: id and industry, without invented region."""
    industry = _INDUSTRY_RU.get(company.industry, company.industry)
    return f"{company.synthetic_u} · {industry}"


def load_payment_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    """Outgoing payments keyed by payer id. A missing file yields nothing."""
    if not path.is_file():
        return {}
    grouped: dict[str, list[dict[str, str]]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            payer = (row.get("PAYER") or "").strip()
            if not payer:
                continue
            amount = _money(row.get("PAY_AMT") or "")
            count = (row.get("PAY_CNT") or "").strip()
            beneficiary = (row.get("BENEFICIARY") or "").strip() or "получатель не указан"
            grouped.setdefault(payer, []).append({
                "beneficiary": beneficiary,
                "amount": amount,
                "count": count,
            })
    return grouped


def build_feed(
    company: CompanyProfile,
    items: Sequence[NewsItem],
    role: Role,
    *,
    as_of: date,
    source: str,
    notice: str,
    loaded_at: str,
    payments: Sequence[dict[str, str]] = (),
) -> dict[str, object]:
    """One company feed after every parsed item is scored.

    ``source`` is ``live`` or ``demo``. ``incoming`` counts parsed items.
    ``ranked`` counts those at or above the show threshold. The items
    list keeps the rest as well, so the screen can scroll the whole parse.
    The model block stays empty.
    """
    scored = parsed_feed(company, list(items), role, as_of=as_of)
    projected = [_item_payload(company, row, role, scored) for row in scored]
    ranked = [row for row in scored if row.relevance is not Relevance.HIDDEN]
    return {
        "company": _company_payload(company, payments),
        "role": {"id": role.value, "label": ROLE_LABEL_RU[role]},
        "as_of": as_of.isoformat(),
        "loaded_at": loaded_at,
        "source": source,
        "notice": notice,
        "incoming": len(items),
        "ranked": len(ranked),
        "items": projected,
    }


def event_headline(company: CompanyProfile, item: NewsItem) -> str:
    """Business title for the feed. It is not the news headline.

    A short stake plus a mild question. The variant follows the URL,
    so neighboring cards about one factor do not repeat one sentence.
    """
    factor = _lead_factor(item)
    if factor is None:
        return "Событие почти не задевает профиль. Стоит ли его открыть?"
    options = _headline_options(company, factor)
    digest = hashlib.sha256(item.source_url.encode("utf-8")).digest()
    return options[digest[0] % len(options)]


def _lead_factor(item: NewsItem) -> Factor | None:
    best: Factor | None = None
    best_level = 0
    for factor in Factor:
        level = item.factors.get(factor, 0)
        if level > best_level:
            best = factor
            best_level = level
    return best


def _headline_options(company: CompanyProfile, factor: Factor) -> tuple[str, ...]:
    if factor is Factor.RATE:
        if company.has_loan and company.has_leasing:
            subject, graph = "кредиту и лизингу", "кредита и лизинга"
        elif company.has_leasing:
            subject, graph = "лизингу", "лизинга"
        elif company.has_loan:
            subject, graph = "кредиту", "кредита"
        else:
            subject, graph = "заёмным деньгам", "заёмных денег"
        return (
            f"Ставка осталась высокой. Что проверить по {subject}?",
            f"Снижение в прогнозе банка не ближайшее. Какой график у {graph}?",
            f"До конца года деньги остаются дорогими. Что сверить по {subject}?",
        )
    if factor is Factor.FX:
        if company.has_foreign_trade:
            return (
                "Курс переписывает расчёты. Хватит ли запаса по контрактам?",
                "Валюта двигает себестоимость. Что зафиксировать в контрактах?",
                "Курс уже в цене контрактов. Проверить условия до следующей выплаты?",
            )
        return (
            "Курс переписывает расчёты. Хватит ли запаса по валюте?",
            "Валюта двигает себестоимость. Что зафиксировать в расчётах?",
            "Курс уже в цене. Проверить валютные платежи?",
        )
    if factor is Factor.INFLATION:
        return (
            "Цены растут быстрее плана. Выдержит ли маржа закупок?",
            "Инфляция догоняет прайс. Успеете пересмотреть закупочные цены?",
        )
    if factor is Factor.DEMAND:
        return (
            "Спрос меняет выручку. Что будет с продажами?",
            "Покупатели замедляются. Хватит ли выручки на ближайший квартал?",
        )
    if factor is Factor.LABOR:
        if company.has_payroll or company.staff_over_100:
            return (
                "Кадры дорожают. Как вырастет фонд оплаты труда?",
                "Рынок труда давит на штат. Что заложить в фонд оплаты труда?",
            )
        return (
            "Кадры дорожают. Как вырастут расходы на персонал?",
            "Рынок труда давит на штат. Что заложить в расходы на людей?",
        )
    if factor is Factor.FUEL:
        return (
            "Топливо двигает себестоимость рейса. Какая доля топлива в расходах?",
            "Цена топлива расходится по видам. На чём работает ваш парк?",
        )
    if factor is Factor.BUDGET:
        return (
            "Бюджетные условия меняются. Затронет ли это контракты?",
            "Государственные деньги пересматривают. Что проверить в контрактах?",
        )
    if factor is Factor.DEBT:
        return (
            "Долговая нагрузка остаётся темой. Какой график у долга?",
            "Обслуживание долга не дешевеет. Есть ли запас по платежам?",
        )
    return (
        "Сырьё меняет закупочную цену. Какая доля сырья в себестоимости?",
        "Биржевая цена дошла до контракта. Можно ли переложить сырьё в тариф?",
    )


def _item_payload(
    company: CompanyProfile,
    scored: ScoredItem,
    role: Role,
    shown: Sequence[ScoredItem],
) -> dict[str, object]:
    view = card_view(company, scored, role=role, client=None, shown=shown)
    item = scored.item
    factors = [
        {"id": factor.value, "label": _FACTOR_RU[factor]}
        for factor in Factor
        if item.factors.get(factor, 0) > 0
    ]
    if scored.relevance is Relevance.IMPORTANT:
        level, label = "high", "Важно"
    elif scored.relevance is Relevance.NOTICE:
        level, label = "mid", "К сведению"
    else:
        level, label = "low", "Ниже порога"
    why = view.consequences
    return {
        "id": item.source_url,
        "title": plain_text(item.title),
        "headline": event_headline(company, item),
        "summary": plain_text(item.summary),
        "published": _russian_date(item.published_on),
        "published_iso": item.published_on.isoformat(),
        "source_name": item.source_name,
        "source_url": item.source_url,
        "score": f"{scored.score:.2f}".replace(".", ","),
        "level": level,
        "label": label,
        "factors": factors,
        "why": why,
        "card": {
            "happened": _reader_fact(plain_text(item.summary) or view.happened),
            "why": _event_link(company, item),
            "consequences": view.consequences,
            "effects": _effects(company, scored),
            "bank": _bank_for_reader(scored),
            "model": view.model,
            "source_name": view.source_name,
            "source_url": view.source_url,
            "signs": _reader_signs(company, item),
        },
    }


def _company_payload(
    company: CompanyProfile,
    payments: Sequence[dict[str, str]],
) -> dict[str, object]:
    industry = _INDUSTRY_RU.get(company.industry, company.industry)
    okved = f", ОКВЭД {company.okved}" if company.okved else ""
    products = _products(company)
    if company.has_foreign_trade:
        trade = company.foreign_trade_countries or "есть, страна не указана"
    else:
        trade = "не отмечена"
    staff = "от 101 сотрудника" if company.staff_over_100 else "до 100 или не указан"
    revenue = _billions(company.revenue_rub) if company.revenue_rub is not None else "не указана"
    return {
        "id": company.synthetic_u,
        "chip": company_chip(company),
        "rows": [
            {"label": "Отрасль", "value": f"{industry}{okved}"},
            {"label": "Выручка", "value": revenue},
            {"label": "Штат", "value": staff},
            {"label": "Продукты в Альфе", "value": products},
            {"label": "ВЭД", "value": trade},
        ],
        "region": company.region,
        "deposit": "Есть в Альфе" if company.has_deposit else "Не отмечены",
        "loan": "Есть в Альфе" if company.has_loan else "Не отмечены",
        "payments": list(payments),
    }


def _products(company: CompanyProfile) -> str:
    named = (
        (company.has_loan, "кредит"),
        (company.has_leasing, "лизинг"),
        (company.has_factoring, "факторинг"),
        (company.has_guarantee, "гарантия"),
        (company.has_deposit, "депозит"),
        (company.has_payroll, "зарплатный проект"),
    )
    labels = [label for flag, label in named if flag]
    if not labels:
        return "не отмечены"
    return ", ".join(labels)


def _billions(revenue_rub: float) -> str:
    rendered = f"{revenue_rub / 1_000_000_000:.1f}".replace(".", ",")
    return f"{rendered} млрд руб."


def _money(raw: str) -> str:
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(cleaned)
    except ValueError:
        return raw.strip() or "сумма не указана"
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} млрд руб.".replace(".", ",")
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.0f} млн руб."
    return f"{amount:.0f} руб."


def analysis_view(result: AgentResult) -> dict[str, object]:
    """Fields the screen can draw. ``download`` is the jury JSON document."""
    claims = getattr(result, "claims", {})
    evidence = getattr(result, "evidence", [])
    trace = getattr(result, "trace", [])
    return {
        "status": result.status,
        "question": result.question,
        "company_id": result.company_id,
        "role": result.role,
        "claims": [
            {"title": name, "text": row["text"], "sources": row["source_ids"]}
            for name, row in claims.items()
        ],
        "gaps": list(result.gaps),
        "trace": [
            {"tool": step.tool, "status": step.status, "detail": step.detail}
            for step in trace
        ],
        "banks": [
            {"id": row.id, "title": row.title, "text": row.text, "url": row.url}
            for row in evidence
            if row.kind == "bank"
        ],
        "download": result.to_json(),
    }


_OPPORTUNITY_MARKS = ("выручк", "доход")
_FUTURE_MARKS = ("ожида", "на конец", "прогноз", "квартал")
_GAP_RU: dict[str, str] = {
    "MAINOKVED_CODE": "код отрасли",
    "REVENUE_COMPANY": "выручка",
    "CL_PRODUCT_LOA_MARK": "кредит",
    "CL_PRODUCT_LEA_MARK": "лизинг",
    "CL_PRODUCT_DEP_MARK": "депозит",
    "FTS_FLAG": "внешнеэкономическая деятельность",
    "AMOUNT_WORKERS_FNS_GRADATION": "численность",
}


def _effects(company: CompanyProfile, scored: ScoredItem) -> dict[str, object]:
    """Three consequence columns from rules and bank forecasts.

    A sentence about revenue or deposit income is an opportunity.
    Every other profile sentence stays a risk. The next column is left
    for the model: bank forecasts stay in the bank block, so the same
    numbers are not copied into a third place. Missing profile facts are
    named in Russian, without column codes.
    """
    risks: list[dict[str, str]] = []
    chances: list[dict[str, str]] = []
    for sentence in _sentences(company_consequence(company, scored.item)):
        folded = sentence.casefold()
        kind_row = {"kind": "fact", "text": sentence}
        if any(mark in folded for mark in _OPPORTUNITY_MARKS):
            chances.append(kind_row)
        else:
            risks.append(kind_row)
    return {
        "risks": risks,
        "opportunities": chances,
        "next": _horizon_rows(scored),
        "gaps": _gap_line(company),
    }


def rate_horizon_present(scored: ScoredItem) -> bool:
    """True when the bank path already fills the next column."""
    return bool(_horizon_rows(scored))


def _horizon_rows(scored: ScoredItem) -> list[dict[str, str]]:
    """The forecast still ahead. Not a task and not a second bank block."""
    for text in _thesis_texts(scored):
        found = re.search(
            r"(\d[\d,]*% на конец \d{4}) и (\d[\d,]*% на конец \d{4})",
            text,
        )
        if found is None:
            continue
        sentence = (
            "Дальше платежи держит прогноз банка: "
            f"{found.group(1)} и только {found.group(2)}."
        )
        return [{"kind": "fact", "text": sentence}]
    return []


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=\.)\s+", text.strip())
    rows: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        if not cleaned.endswith("."):
            cleaned = f"{cleaned}."
        rows.append(cleaned)
    return rows


def _thesis_texts(scored: ScoredItem) -> list[str]:
    card = scored.bank_card
    if card is None or not card.fresh:
        return []
    rows = list(cited_theses(card))
    top = _leading_factor(scored.item)
    if top is not None:
        matched = [row for row in rows if row.factor is top]
        if matched:
            rest = [row for row in rows if row.factor is not top]
            rows = matched + rest
    return [row.text.strip() for row in rows if row.text.strip()]


def _gap_line(company: CompanyProfile) -> str:
    names = [_GAP_RU[name] for name in company.missing_fields if name in _GAP_RU]
    if not names:
        return ""
    return "Каких данных нет: " + ", ".join(names) + "."


_SIGN_RU: dict[str, str] = {
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


def _reader_fact(text: str) -> str:
    """One sentence with the event's number, not the article lead."""
    sentences = _sentences(text)
    for sentence in sentences:
        folded = sentence.casefold()
        has_number = any(char.isdigit() for char in sentence)
        if has_number and ("ставк" in folded or "%" in sentence or "руб" in folded):
            return sentence
    for sentence in sentences:
        if len(sentence) >= 40:
            return sentence
    return sentences[0] if sentences else text


def _event_link(company: CompanyProfile, item: NewsItem) -> str:
    """How this event touches the open products. Not a company passport."""
    parts: list[str] = []
    if item.factors.get(Factor.RATE, 0) > 0 and (company.has_loan or company.has_leasing):
        names: list[str] = []
        if company.has_loan:
            names.append("кредиту")
        if company.has_leasing:
            names.append("лизингу")
        joined = " и ".join(names)
        parts.append(f"Ставка бьёт по уже открытым {joined}.")
    if item.factors.get(Factor.FX, 0) > 0 and company.has_foreign_trade:
        where = company.foreign_trade_countries or "внешние контракты"
        parts.append(f"Торговля: {where}. Валюта закупок отсюда не видна.")
    if not parts:
        return _company_link(company)
    return " ".join(parts)


def _company_link(company: CompanyProfile) -> str:
    """Profile facts that tie the company to the event, without scores."""
    industry = _INDUSTRY_RU.get(company.industry, company.industry)
    okved = f", ОКВЭД {company.okved}" if company.okved else ""
    parts = [f"Компания: {industry}{okved}."]
    products = _products(company)
    if products != "не отмечены":
        parts.append(f"В Альфе: {products}.")
    if company.staff_over_100:
        parts.append("Штат от 101 человека.")
    if company.has_foreign_trade and company.foreign_trade_countries:
        parts.append(f"Торговля: {company.foreign_trade_countries}.")
    return " ".join(parts)


def _reader_signs(company: CompanyProfile, item: NewsItem) -> str:
    """Human names of the profile facts that raised this item."""
    labels = [
        _SIGN_RU[name]
        for name in csv_fields_raising_score(company, item)
        if name in _SIGN_RU
    ]
    if not labels:
        return ""
    return "На отбор повлияло: " + ", ".join(labels) + "."


def _bank_for_reader(scored: ScoredItem) -> str:
    """Bank title, date, and theses. File names and page numbers stay out."""
    card = scored.bank_card
    if card is None or not card.fresh:
        return "Свежей позиции банка по этой теме нет."
    rows = list(cited_theses(card))
    top = _leading_factor(scored.item)
    if top is not None:
        matched = [row for row in rows if row.factor is top]
        if matched:
            rest = [row for row in rows if row.factor is not top]
            rows = matched + rest
    published = card.published_on.strftime("%d.%m.%Y")
    sentences = [_dated_thesis(row.text.strip(), scored) for row in rows if row.text.strip()]
    head = f"{card.title}. Материал банка от {published}."
    if not sentences:
        return head
    return head + " " + " ".join(sentences)


def _dated_thesis(text: str, scored: ScoredItem) -> str:
    """A forecast of 23 October is past once the news is on or after that day."""
    if scored.item.published_on >= date(2026, 10, 23):
        return text.replace("ожидает паузу 23 октября", "тогда ожидал паузу 23 октября")
    return text


def _leading_factor(item: NewsItem) -> Factor | None:
    if not item.factors:
        return None
    top = max(item.factors, key=item.factors.get)
    if isinstance(top, Factor):
        return top
    return None


def _reasons_ru(reasons: tuple[str, ...]) -> str:
    """Show factor names in Russian. The rest of the reason stays as scored."""
    text = "; ".join(reasons)
    for factor, label in _FACTOR_RU.items():
        text = text.replace(factor.name, label)
    return text


def _russian_date(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"
