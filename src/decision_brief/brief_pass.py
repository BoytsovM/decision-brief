"""One preparation pass for a company brief.

The seven steps always run in the same order and are written to the log.
Bank PDFs are not opened. A missing card is reported as-is. One text
completion covers the top shown news. Hidden news is not sent.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from decision_brief.companies import GroupSummary, load_companies, summarize_groups
from decision_brief.conclusion import (
    ModelCallError,
    ModelClient,
    build_model_prompt,
    client_from_env,
    review_model_phrases,
    unsupported_numbers,
)
from decision_brief.counterparties import CounterpartyShare, counterparties_for_company
from decision_brief.models import CompanyProfile, Factor, NewsItem, ScoredItem
from decision_brief.pipeline import explain_for_role
from decision_brief.roles import ROLE_LABEL_RU, Role, rank_for_role, weight_source

_TOP_SHOWN = 3
_NO_CARD = "Свежей карточки банка по этому фактору нет."

_FLAGS: tuple[tuple[str, str], ...] = (
    ("has_loan", "кредит"),
    ("has_leasing", "лизинг"),
    ("has_factoring", "факторинг"),
    ("has_guarantee", "гарантия"),
    ("has_deposit", "депозит"),
    ("has_payroll", "зарплатный проект"),
    ("has_foreign_trade", "внешнеэкономическая деятельность"),
    ("foreign_owner", "иностранный собственник"),
    ("staff_over_100", "крупный штат"),
    ("rapid_growth", "стремительный рост"),
)


@dataclass(frozen=True)
class BriefPass:
    """Russian brief and the seven-step log of one preparation pass."""

    answer: str
    log: tuple[str, ...]
    discarded_phrases: tuple[str, ...]


def prepare_brief(
    company_id: str,
    items: Sequence[NewsItem],
    role: Role,
    *,
    companies_path: Path,
    payments_path: Path,
    as_of: date,
    client: ModelClient | None = None,
    question: str = "",
    same_profile: bool = False,
) -> BriefPass:
    """Run the seven preparation steps once and return the brief.

    ``client`` is called at most once, and only with news the ranker
    already showed. A follow-up passes the same company id, the same
    files, and a new ``question``. ``same_profile`` marks that follow-up
    in the log. No bank PDF is opened when the fresh card is missing.
    """
    log: list[str] = []
    company, group = _load_profile(company_id, companies_path)
    _log_profile(log, company_id, company, group, same_profile=same_profile)
    _log_role(log, role)
    shown = _log_ranking(log, company, items, role, as_of=as_of)
    _log_card(log, shown)
    counterparties = _log_counterparties(
        log,
        company,
        payments_path=payments_path,
        companies_path=companies_path,
    )
    conclusion, discarded, prompt = _log_model_call(
        log,
        company,
        shown,
        role,
        question=question,
        client=client,
    )
    answer = _render(
        company_id,
        company,
        group,
        role,
        shown,
        counterparties,
        conclusion,
        question,
    )
    _log_checks(log, answer, prompt, shown)
    return BriefPass(
        answer=answer,
        log=tuple(log),
        discarded_phrases=discarded,
    )


def prepare_follow_up(
    company_id: str,
    items: Sequence[NewsItem],
    role: Role,
    question: str,
    *,
    companies_path: Path,
    payments_path: Path,
    as_of: date,
    client: ModelClient | None = None,
) -> BriefPass:
    """Run the seven steps again for one new question.

    The company id and the files stay the same, so the profile is the
    same company. Hidden news is still left out of the single call.
    """
    return prepare_brief(
        company_id,
        items,
        role,
        companies_path=companies_path,
        payments_path=payments_path,
        as_of=as_of,
        client=client,
        question=question,
        same_profile=True,
    )


def _load_profile(
    company_id: str,
    companies_path: Path,
) -> tuple[CompanyProfile | None, GroupSummary | None]:
    requested = company_id.strip()
    company = next(
        (
            row
            for row in load_companies(companies_path)
            if row.synthetic_u == requested
        ),
        None,
    )
    group_id = _group_id(requested, companies_path)
    if not group_id:
        return company, None
    group = next(
        (
            item
            for item in summarize_groups(companies_path)
            if item.group_id == group_id
        ),
        None,
    )
    return company, group


def _group_id(company_id: str, companies_path: Path) -> str:
    """Read GROUP_ID for one company. An empty cell means no group."""
    with companies_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            if (row.get("SYNTHETIC_U") or "").strip() != company_id:
                continue
            return (row.get("GROUP_ID") or "").strip()
    return ""


def _log_profile(
    log: list[str],
    company_id: str,
    company: CompanyProfile | None,
    group: GroupSummary | None,
    *,
    same_profile: bool,
) -> None:
    log.append("1. Профиль компании и группы")
    if same_profile:
        log.append(f"Профиль тот же: {company_id.strip()}.")
    if company is None:
        log.append(f"Компания {company_id.strip()} в файле не найдена.")
        return
    log.append(f"Признаки компании: {_features(company)}")
    log.append(_group_line(group))


def _log_role(log: list[str], role: Role) -> None:
    log.append("2. Роль")
    log.append(f"Роль: {ROLE_LABEL_RU[role]}.")
    if weight_source().assumed:
        log.append("Множители роли: допущение в коде.")
        return
    log.append("Множители роли: лист весов.")


def _log_ranking(
    log: list[str],
    company: CompanyProfile | None,
    items: Sequence[NewsItem],
    role: Role,
    *,
    as_of: date,
) -> list[ScoredItem]:
    log.append("3. Ранжирование новостей")
    if company is None:
        log.append("Ранжирование не выполнено: компания не найдена.")
        return []
    ranked = rank_for_role(company, list(items), role, as_of=as_of)
    shown = ranked[:_TOP_SHOWN]
    if not shown:
        log.append("Показанных новостей нет.")
    for row in shown:
        log.append(f"Источник: {row.item.source_name} {row.item.source_url}")
    hidden = len(items) - len(ranked)
    log.append(f"Скрыто и в модель не отправлено: {hidden}.")
    extra = len(ranked) - len(shown)
    if extra:
        log.append(f"Ниже верхней тройки, в этот проход не входят: {extra}.")
    return shown


def _log_card(log: list[str], shown: Sequence[ScoredItem]) -> None:
    log.append("4. Свежая карточка по главному фактору")
    if not shown:
        log.append(_NO_CARD)
        return
    card = shown[0].bank_card
    factor = _main_factor(shown[0].item)
    factor_name = factor.name if factor is not None else "нет"
    if card is None or not card.fresh:
        log.append(f"Главный фактор: {factor_name}. {_NO_CARD}")
        return
    published = card.published_on.strftime("%d.%m.%Y")
    log.append(
        f"Главный фактор: {factor_name}. "
        f"Карточка {card.card_id}, {card.filename}, {published}."
    )


def _log_counterparties(
    log: list[str],
    company: CompanyProfile | None,
    *,
    payments_path: Path,
    companies_path: Path,
) -> list[CounterpartyShare]:
    log.append("5. Контрагенты с долей от 10%")
    if company is None:
        log.append("Контрагентов с долей от 10% нет.")
        return []
    rows = counterparties_for_company(
        company.synthetic_u,
        payments_path,
        companies_path,
    )
    log.append(_counterparty_text(rows))
    return rows


def _log_model_call(
    log: list[str],
    company: CompanyProfile | None,
    shown: Sequence[ScoredItem],
    role: Role,
    *,
    question: str,
    client: ModelClient | None,
) -> tuple[str, tuple[str, ...], str]:
    log.append("6. Вызов модели")
    active = client if client is not None else client_from_env()
    if company is None:
        log.append("Вызов модели не выполнен: компания не найдена.")
        _log_discarded(log, ())
        return "", (), ""
    if not shown:
        log.append("Вызов модели не выполнен: показанных новостей нет.")
        _log_discarded(log, ())
        return "", (), ""
    if active is None:
        log.append("Вызов модели не выполнен: клиент не задан.")
        _log_discarded(log, ())
        return "", (), ""
    prompt = _prompt(company, shown, role, question)
    log.append(f"Вызов модели: один, новостей в запросе: {len(shown)}.")
    try:
        raw = active.complete(prompt)
    except ModelCallError:
        log.append("Вызов модели не выполнен.")
        _log_discarded(log, ())
        return "", (), prompt
    conclusion, discarded = review_model_phrases(raw, prompt)
    _log_discarded(log, discarded)
    return conclusion, discarded, prompt


def _log_discarded(log: list[str], discarded: tuple[str, ...]) -> None:
    log.append("Отброшенные фразы:")
    if not discarded:
        log.append("нет")
        return
    log.extend(discarded)


def _log_checks(
    log: list[str],
    answer: str,
    prompt: str,
    shown: Sequence[ScoredItem],
) -> None:
    log.append("7. Проверка")
    log.append(_check_numbers(answer, prompt))
    log.append(_check_bank(answer))
    log.append(_check_link(answer, shown))


def _render(
    company_id: str,
    company: CompanyProfile | None,
    group: GroupSummary | None,
    role: Role,
    shown: Sequence[ScoredItem],
    counterparties: Sequence[CounterpartyShare],
    conclusion: str,
    question: str,
) -> str:
    if company is None:
        return f"Компания {company_id.strip()} в файле не найдена."
    blocks = [
        "\n".join(
            (
                f"Компания {company.synthetic_u} ({company.industry}).",
                f"Признаки компании. {_features(company)}",
                _group_line(group),
                f"Роль. {ROLE_LABEL_RU[role]}.",
            )
        )
    ]
    if shown:
        blocks.extend(_card_without_model(company, row, role) for row in shown)
    else:
        blocks.append(f"Как оценивает банк. {_NO_CARD}")
    blocks.append(_counterparty_text(counterparties))
    asked = " ".join(question.split())
    if asked:
        blocks.append(f"Вопрос. {asked}")
    model_line = "Вывод модели."
    if conclusion.strip():
        model_line = f"Вывод модели. {conclusion.strip()}"
    tail = [model_line]
    if shown:
        links = ", ".join(row.item.source_url for row in shown)
        tail.append(f"Источник вывода. {links}")
    blocks.append("\n".join(tail))
    return "\n\n".join(blocks)


def _card_without_model(
    company: CompanyProfile,
    scored: ScoredItem,
    role: Role,
) -> str:
    card = explain_for_role(company, scored, role)
    lines = [
        line for line in card.splitlines() if not line.startswith("Вывод модели")
    ]
    return "\n".join(lines)


def _prompt(
    company: CompanyProfile,
    shown: Sequence[ScoredItem],
    role: Role,
    question: str,
) -> str:
    chunks: list[str] = []
    asked = " ".join(question.split())
    if asked:
        chunks.append(f"Вопрос пользователя: {asked}")
    for index, scored in enumerate(shown, start=1):
        chunks.append(f"Новость {index}.")
        chunks.append(build_model_prompt(company, scored, role=role))
    return "\n".join(chunks)


def _features(company: CompanyProfile) -> str:
    parts = [f"отрасль {company.industry}"]
    if company.okved:
        parts.append(f"ОКВЭД {company.okved}")
    if company.revenue_rub is not None:
        parts.append(f"выручка {_plain_number(company.revenue_rub)}")
    parts.extend(
        label for attr, label in _FLAGS if getattr(company, attr) is True
    )
    return ", ".join(parts)


def _group_line(group: GroupSummary | None) -> str:
    if group is None:
        return "Группа не указана."
    large = "да" if group.passes_large_revenue else "нет"
    revenue = _plain_number(group.revenue_rub)
    return (
        f"Группа {group.group_id}: выручка {revenue} руб., "
        f"юрлиц {group.legal_entity_count}, сумма от 15 млрд: {large}."
    )


def _counterparty_text(rows: Sequence[CounterpartyShare]) -> str:
    if not rows:
        return "Контрагентов с долей от 10% нет."
    parts = [
        (
            f"{row.counterparty_id}, доля {_percent(row.share)}, "
            f"сумма {_plain_number(row.amount_rub)} руб., "
            f"платежей {row.payment_count}"
        )
        for row in rows
    ]
    return "Контрагенты с долей от 10%: " + "; ".join(parts) + "."


def _main_factor(item: NewsItem) -> Factor | None:
    if not item.factors:
        return None
    top = max(item.factors, key=lambda factor: item.factors[factor])
    if isinstance(top, Factor):
        return top
    return None


def _check_numbers(answer: str, prompt: str) -> str:
    missing = unsupported_numbers(_model_line(answer), prompt)
    if not missing:
        return "Проверка чисел: каждое число вывода есть во входе."
    listed = ", ".join(missing)
    return f"Проверка чисел: не пройдена, лишние числа: {listed}."


def _check_bank(answer: str) -> str:
    lines = answer.splitlines()
    bank = [
        index
        for index, line in enumerate(lines)
        if line.startswith("Как оценивает банк.")
    ]
    model = [
        index
        for index, line in enumerate(lines)
        if line.startswith("Вывод модели")
    ]
    separated = len(model) == 1 and bool(bank) and max(bank) < model[0]
    if separated:
        return "Проверка позиции банка: позиция банка отделена от вывода модели."
    return (
        "Проверка позиции банка: не пройдена, "
        "вывод модели не отделён от позиции банка."
    )


def _check_link(answer: str, shown: Sequence[ScoredItem]) -> str:
    if not shown:
        return "Проверка ссылки: показанных новостей нет, ссылку поставить не на что."
    missing = any(row.item.source_url not in answer for row in shown)
    if missing or "Источник вывода." not in answer:
        return "Проверка ссылки: не пройдена, нет ссылки на новость."
    return "Проверка ссылки: у вывода есть ссылка."


def _model_line(answer: str) -> str:
    for line in answer.splitlines():
        if line.startswith("Вывод модели"):
            return line
    return ""


def _plain_number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(rounded)
    rendered = format(value, "f").rstrip("0").rstrip(".")
    return rendered or "0"


def _percent(share: float) -> str:
    rounded = round(share * 100, 1)
    if abs(rounded - round(rounded)) < 1e-9:
        return f"{int(round(rounded))}%"
    return f"{rounded:.1f}".replace(".", ",") + "%"
