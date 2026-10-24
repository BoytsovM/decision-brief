"""Feed for a person in a role. The company score stays in ``score_item``.

A single coefficient per role cannot change the order of one company
feed, so the multiplier is the strength-weighted mean of per-factor
weights. The same 0.6 and 0.3 thresholds then run on the product.
When the analyst workbook is missing, the multipliers below are an
explicit assumption, not a fitted scale.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

from decision_brief.bank_cards import latest_card_for
from decision_brief.counterparties import CounterpartyShare
from decision_brief.models import (
    BankCard,
    CompanyProfile,
    Factor,
    NewsItem,
    Relevance,
    ScoredItem,
)
from decision_brief.scoring import relevance_for, score_item

# Same 10% gate as counterparties_for_company. A smaller share never
# becomes a reason, even when the caller passes it in.
_MIN_COUNTERPARTY_SHARE = 0.10

_WORKBOOK_NAME = "Аналитика хакатона Альфа (таблицы).xlsx"
_SHEET_NAME = "Веса ролей"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class Role(Enum):
    """Person who reads the feed. Not a second legal entity."""

    TREASURER = "treasurer"
    CHIEF_ACCOUNTANT = "chief_accountant"
    OWNER = "owner"


ROLE_LABEL_RU: dict[Role, str] = {
    Role.TREASURER: "казначей",
    Role.CHIEF_ACCOUNTANT: "главный бухгалтер",
    Role.OWNER: "собственник",
}

# 1.0 keeps the company score. A lower number is a haircut.
# Chief-accountant budget is the stand-in for regulation: Factor has
# no regulation column. It stays below the owner's government-order
# weight on the same column. Payroll is LABOR.
_ASSUMED: dict[Role, dict[Factor, float]] = {
    Role.TREASURER: {
        Factor.RATE: 1.0,
        Factor.FX: 1.0,
        Factor.INFLATION: 0.55,
        Factor.DEMAND: 0.60,
        Factor.LABOR: 0.40,
        Factor.FUEL: 0.45,
        Factor.BUDGET: 0.50,
        Factor.DEBT: 1.0,
        Factor.COMMODITY: 0.40,
    },
    Role.CHIEF_ACCOUNTANT: {
        Factor.RATE: 0.55,
        Factor.FX: 0.45,
        Factor.INFLATION: 0.60,
        Factor.DEMAND: 0.40,
        Factor.LABOR: 1.0,
        Factor.FUEL: 0.40,
        Factor.BUDGET: 0.75,
        Factor.DEBT: 0.50,
        Factor.COMMODITY: 0.35,
    },
    Role.OWNER: {
        Factor.RATE: 0.45,
        Factor.FX: 0.45,
        Factor.INFLATION: 0.55,
        Factor.DEMAND: 1.0,
        Factor.LABOR: 0.50,
        Factor.FUEL: 0.40,
        Factor.BUDGET: 1.0,
        Factor.DEBT: 0.40,
        Factor.COMMODITY: 0.45,
    },
}

_INDUSTRY_RU: dict[str, str] = {
    "fuel": "нефтегаза",
    "metals": "металлургии",
    "agri": "агропрома",
    "housing": "жилищного строительства",
    "infrastructure": "инфраструктурного строительства",
    "real_estate": "недвижимости",
    "auto": "автопрома",
    "retail": "розницы",
    "horeca": "общепита",
    "transport": "грузоперевозок",
    "energy": "энергетики",
    "it": "ИТ",
    "finance": "финансов",
    "machinery": "машиностроения",
    "chemicals": "химии",
    "wholesale": "оптовой торговли",
    "services": "услуг",
}

_FACTOR_CODE: dict[str, Factor] = {
    "f1": Factor.RATE,
    "f2": Factor.FX,
    "f3": Factor.INFLATION,
    "f4": Factor.DEMAND,
    "f5": Factor.LABOR,
    "f6": Factor.FUEL,
    "f7": Factor.BUDGET,
    "f8": Factor.DEBT,
    "f9": Factor.COMMODITY,
}

_FACTOR_STEMS: tuple[tuple[str, Factor], ...] = (
    ("ключев", Factor.RATE),
    ("ставк", Factor.RATE),
    ("курс", Factor.FX),
    ("инфляц", Factor.INFLATION),
    ("спрос", Factor.DEMAND),
    ("потреблен", Factor.DEMAND),
    ("фонд оплат", Factor.LABOR),
    ("зарплат", Factor.LABOR),
    ("фот", Factor.LABOR),
    ("топлив", Factor.FUEL),
    ("госзаказ", Factor.BUDGET),
    ("госконтракт", Factor.BUDGET),
    ("регулир", Factor.BUDGET),
    ("бюджет", Factor.BUDGET),
    ("долг", Factor.DEBT),
    ("офз", Factor.DEBT),
    ("сырь", Factor.COMMODITY),
)


@dataclass(frozen=True)
class WeightSource:
    """Where the role multipliers came from.

    ``assumed`` is true when the workbook is missing or the sheet
    «Веса ролей» cannot be read. ``note`` is for logs.
    """

    weights: dict[Role, dict[Factor, float]]
    assumed: bool
    path: Path | None
    note: str


def assumed_role_weights() -> dict[Role, dict[Factor, float]]:
    """Return the in-code multipliers, one copy per call.

    Treasurer keeps rate, FX and debt. The chief accountant keeps
    payroll and a lower budget weight that stands in for regulation.
    The owner keeps demand and government orders.
    """
    return {role: dict(row) for role, row in _ASSUMED.items()}


def find_role_workbook() -> Path | None:
    """Return the analyst workbook if it sits next to the repo.

    The search is a short list of paths. It does not walk the disk.
    """
    for path in _workbook_candidates():
        if path.is_file():
            return path
    return None


def load_role_weights(path: Path) -> dict[Role, dict[Factor, float]] | None:
    """Read sheet «Веса ролей» and scale each role by its own maximum.

    The result is None when the file is not a workbook, the sheet is
    missing, or a role has no positive weight. Missing factors become
    0 before that scaling, so an unlisted factor does not keep the
    company score. Values may be written with a comma or a dot.
    """
    try:
        rows = _sheet_rows(path, _SHEET_NAME)
    except (
        OSError,
        zipfile.BadZipFile,
        ET.ParseError,
        KeyError,
        ValueError,
        IndexError,
    ):
        return None
    if not rows:
        return None
    return _weights_from_rows(rows)


@lru_cache(maxsize=1)
def weight_source() -> WeightSource:
    """Load the workbook once, or keep the in-code assumption."""
    path = find_role_workbook()
    assumed = assumed_role_weights()
    if path is None:
        return WeightSource(
            weights=assumed,
            assumed=True,
            path=None,
            note=(
                "Workbook was not found. Multipliers are the in-code "
                "assumption."
            ),
        )
    loaded = load_role_weights(path)
    if loaded is None:
        return WeightSource(
            weights=assumed,
            assumed=True,
            path=path,
            note="Workbook was found but the role sheet could not be read.",
        )
    return WeightSource(
        weights=loaded,
        assumed=False,
        path=path,
        note="Weights come from the role sheet.",
    )


def role_multiplier(role: Role, item: NewsItem) -> float:
    """Strength-weighted mean of this role's factor weights.

    An item with no factors returns 1, so a company score that came
    only from coverage or an industry mention is left as ``score_item``
    computed it. The mean stays in 0..1 when every weight does.
    """
    weights = weight_source().weights[role]
    total = 0.0
    mass = 0
    for factor, strength in item.factors.items():
        if strength <= 0:
            continue
        total += weights[factor] * strength
        mass += strength
    if mass == 0:
        return 1.0
    return total / mass


def counterparty_reasons(
    item: NewsItem,
    counterparties: Sequence[CounterpartyShare],
) -> tuple[str, ...]:
    """Reasons for counterparties the news names, share at least 10%.

    The id must stand as its own token in the title or the summary.
    A smaller share is ignored. Order follows ``counterparties``.
    """
    reasons: list[str] = []
    for row in counterparties:
        if row.share < _MIN_COUNTERPARTY_SHARE:
            continue
        if not _news_names(item, row.counterparty_id):
            continue
        percent = _share_percent(row.share)
        reasons.append(
            f"Контрагент {row.counterparty_id}, доля {percent} платежей: "
            "новость про него."
        )
    return tuple(reasons)


def company_consequence(company: CompanyProfile, item: NewsItem) -> str:
    """Russian effect of this item on this profile.

    Each sentence names the industry and the flags that make the factor
    matter. Two industries do not share one stock sentence.
    """
    industry = _INDUSTRY_RU.get(company.industry, company.industry)
    parts: list[str] = []
    for factor in Factor:
        if item.factors.get(factor, 0) <= 0:
            continue
        parts.append(_FACTOR_LINE[factor](company, industry))
    if item.mentions_industry:
        parts.append(f"Новость прямо называет отрасль: {industry}.")
    if not parts:
        return (
            f"Для {industry} ни один фактор новости не даёт отдельного следствия."
        )
    return " ".join(parts)


def score_for_role(
    company: CompanyProfile,
    item: NewsItem,
    role: Role,
    *,
    as_of: date,
    counterparties: Sequence[CounterpartyShare] = (),
) -> tuple[float, tuple[str, ...]]:
    """Return the company score times the role weight, plus reasons.

    Thresholds are not applied here. A material older than a year stays
    at 0 because ``score_item`` already returns 0. Counterparty reasons
    are appended only for a named id with a share of at least 10%.
    """
    company_score, reasons = score_item(company, item, as_of=as_of)
    adjusted = company_score * role_multiplier(role, item)
    extra = counterparty_reasons(item, counterparties)
    return adjusted, reasons + extra


def score_every_item(
    company: CompanyProfile,
    items: list[NewsItem],
    role: Role,
    *,
    as_of: date,
    counterparties: Sequence[CounterpartyShare] = (),
) -> list[ScoredItem]:
    """Score every parsed item, including those below the show threshold.

    Order is the multiplied score, highest first. From 0.6 the item is
    important, from 0.3 it is a notice, and below that it stays in the
    list with ``Relevance.HIDDEN``. A material older than a year stays
    at 0. The attached bank card is the newest fresh card for the
    strongest factor.
    """
    scored: list[ScoredItem] = []
    for item in items:
        value, reasons = score_for_role(
            company,
            item,
            role,
            as_of=as_of,
            counterparties=counterparties,
        )
        scored.append(
            ScoredItem(
                item=item,
                score=value,
                relevance=relevance_for(value),
                reasons=reasons,
                bank_card=_bank_card_for(item),
            )
        )
    scored.sort(key=lambda row: row.score, reverse=True)
    return scored


def rank_for_role(
    company: CompanyProfile,
    items: list[NewsItem],
    role: Role,
    *,
    as_of: date,
    counterparties: Sequence[CounterpartyShare] = (),
) -> list[ScoredItem]:
    """Order a feed for one person. Hidden items drop out.

    The label uses the multiplied score. From 0.6 the item is important,
    from 0.3 it is a notice, and below that it is hidden. The attached
    bank card is the newest fresh card for the strongest factor.
    """
    scored = score_every_item(
        company,
        items,
        role,
        as_of=as_of,
        counterparties=counterparties,
    )
    return [row for row in scored if row.relevance is not Relevance.HIDDEN]


def _workbook_candidates() -> tuple[Path, ...]:
    repo = Path(__file__).resolve().parents[2]
    home = Path.home()
    return (
        repo / _WORKBOOK_NAME,
        repo / "data" / _WORKBOOK_NAME,
        repo.parent / _WORKBOOK_NAME,
        home / "Desktop" / _WORKBOOK_NAME,
        home / "Downloads" / _WORKBOOK_NAME,
        home / "Downloads" / "Telegram Desktop" / _WORKBOOK_NAME,
        Path(r"C:\Загрузки\Yandex загрузки") / _WORKBOOK_NAME,
    )


def _bank_card_for(item: NewsItem) -> BankCard | None:
    """Newest fresh card for the strongest factor, as in the company feed."""
    if not item.factors:
        return None
    top = max(item.factors, key=lambda factor: item.factors[factor])
    if not isinstance(top, Factor):
        return None
    return latest_card_for(top)


def _news_names(item: NewsItem, counterparty_id: str) -> bool:
    token = counterparty_id.strip()
    if not token:
        return False
    haystack = f"{item.title}\n{item.summary}"
    pattern = rf"(?<!\w){re.escape(token)}(?!\w)"
    return re.search(pattern, haystack) is not None


def _share_percent(share: float) -> str:
    rounded = round(share * 100, 1)
    if abs(rounded - round(rounded)) < 1e-9:
        return f"{int(round(rounded))}%"
    return f"{rounded:.1f}".replace(".", ",") + "%"


def _rate_line(company: CompanyProfile, industry: str) -> str:
    costs: list[str] = []
    if company.has_loan:
        costs.append("кредиту")
    if company.has_leasing:
        costs.append("лизингу")
    if company.has_factoring:
        costs.append("факторингу")
    if costs:
        tail = ""
        if company.has_deposit:
            tail = " Доход по депозиту при этом растёт вместе со ставкой."
        return (
            f"Для {industry} ставка бьёт по {_join_ru(costs)}: "
            f"платежи зависят от стоимости денег.{tail}"
        )
    if company.has_deposit:
        return (
            f"Для {industry} ставка меняет доход по депозиту: "
            "кредита и лизинга в профиле нет."
        )
    if company.rapid_growth:
        return (
            f"Для {industry} ставка бьёт по фондированию: "
            "в профиле отмечен стремительный рост, а кредита и лизинга нет."
        )
    return (
        f"Для {industry} ставка проходит через отраслевую базу: "
        "кредита и лизинга в профиле нет."
    )


def _fx_line(company: CompanyProfile, industry: str) -> str:
    if company.has_foreign_trade:
        countries = company.foreign_trade_countries.strip()
        if countries:
            return (
                f"Курс меняет расчёты {industry}: внешнеэкономическая "
                f"деятельность есть в профиле ({countries})."
            )
        return (
            f"Курс меняет расчёты {industry}: внешнеэкономическая "
            "деятельность есть в профиле."
        )
    if company.foreign_owner:
        return (
            f"Курс меняет потоки {industry}: в профиле иностранный собственник."
        )
    return (
        f"Курс для {industry} идёт от отраслевой базы: "
        "флага внешнеэкономической деятельности нет."
    )


def _inflation_line(company: CompanyProfile, industry: str) -> str:
    return f"Инфляция переписывает цены и издержки {industry}."


def _demand_line(company: CompanyProfile, industry: str) -> str:
    if company.industry == "horeca":
        return "Спрос прямо меняет выручку общепита: поток гостей и средний чек."
    if company.industry == "retail":
        return "Спрос прямо меняет выручку розницы: трафик и средний чек."
    return f"Спрос меняет загрузку и выручку {industry}."


def _labor_line(company: CompanyProfile, industry: str) -> str:
    if company.has_payroll or company.staff_over_100:
        return (
            f"Фонд оплаты {industry} под давлением: в профиле есть "
            "зарплатный проект или штат больше 100 человек."
        )
    return (
        f"Рынок труда {industry} влияет на найм: зарплатного проекта "
        "и крупного штата в профиле нет."
    )


def _fuel_line(company: CompanyProfile, industry: str) -> str:
    if company.industry == "transport":
        return "Топливо входит в себестоимость грузоперевозок."
    if company.industry == "energy":
        return "Топливо для энергетики входит в себестоимость генерации."
    return (
        f"Топливо для {industry} остаётся косвенным расходом, "
        "не основой себестоимости парка."
    )


def _budget_line(company: CompanyProfile, industry: str) -> str:
    if company.has_guarantee:
        return (
            f"Госзаказ и бюджет для {industry}: банковские гарантии "
            "указывают на контракты с государством."
        )
    return (
        f"Бюджет и госзаказ для {industry} без гарантий в профиле "
        "остаются отраслевым каналом."
    )


def _debt_line(company: CompanyProfile, industry: str) -> str:
    if company.has_loan:
        return (
            f"Долговой рынок меняет стоимость заимствований {industry}: "
            "кредит в профиле усиливает канал."
        )
    return f"Долговой рынок меняет стоимость заимствований {industry}."


def _commodity_line(company: CompanyProfile, industry: str) -> str:
    countries = company.foreign_trade_countries.casefold()
    if "китай" in countries and company.industry in {"metals", "fuel", "agri"}:
        return (
            f"Сырьевые цены и юань меняют продажи {industry} в Китай: "
            "страна есть в профиле."
        )
    return f"Сырьевые цены меняют входные затраты {industry}."


_FactorLine = Callable[[CompanyProfile, str], str]

_FACTOR_LINE: dict[Factor, _FactorLine] = {
    Factor.RATE: _rate_line,
    Factor.FX: _fx_line,
    Factor.INFLATION: _inflation_line,
    Factor.DEMAND: _demand_line,
    Factor.LABOR: _labor_line,
    Factor.FUEL: _fuel_line,
    Factor.BUDGET: _budget_line,
    Factor.DEBT: _debt_line,
    Factor.COMMODITY: _commodity_line,
}


def _join_ru(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} и {parts[1]}"
    return ", ".join(parts[:-1]) + " и " + parts[-1]


def _weights_from_rows(
    rows: Sequence[Sequence[str]],
) -> dict[Role, dict[Factor, float]] | None:
    table = [list(row) for row in rows]
    parsed = _from_factor_rows(table)
    if parsed is not None:
        return parsed
    return _from_role_rows(table)


def _from_factor_rows(
    rows: list[list[str]],
) -> dict[Role, dict[Factor, float]] | None:
    header_index, role_columns = _header(rows, _role_from_label)
    if header_index is None:
        return None
    raw: dict[Role, dict[Factor, float]] = {role: {} for role in role_columns.values()}
    for row in rows[header_index + 1 :]:
        factor = _first(row, _factor_from_label)
        if factor is None:
            continue
        for column, role in role_columns.items():
            if column >= len(row):
                continue
            number = _number(row[column])
            if number is None:
                continue
            raw[role][factor] = number
    return _complete(raw)


def _from_role_rows(
    rows: list[list[str]],
) -> dict[Role, dict[Factor, float]] | None:
    header_index, factor_columns = _header(rows, _factor_from_label)
    if header_index is None:
        return None
    raw: dict[Role, dict[Factor, float]] = {}
    for row in rows[header_index + 1 :]:
        role = _first(row, _role_from_label)
        if role is None:
            continue
        raw.setdefault(role, {})
        for column, factor in factor_columns.items():
            if column >= len(row):
                continue
            number = _number(row[column])
            if number is None:
                continue
            raw[role][factor] = number
    return _complete(raw)


def _header(rows: list[list[str]], reader):
    for index, row in enumerate(rows[:15]):
        found = {}
        for column, cell in enumerate(row):
            parsed = reader(cell)
            if parsed is not None and parsed not in found.values():
                found[column] = parsed
        if len(found) >= 2:
            return index, found
    return None, {}


def _first(row: Sequence[str], reader):
    for cell in row:
        parsed = reader(cell)
        if parsed is not None:
            return parsed
    return None


def _complete(
    raw: dict[Role, dict[Factor, float]],
) -> dict[Role, dict[Factor, float]] | None:
    if set(raw) != set(Role):
        return None
    normalized: dict[Role, dict[Factor, float]] = {}
    for role in Role:
        factors = raw[role]
        if not factors:
            return None
        filled = {factor: factors.get(factor, 0.0) for factor in Factor}
        peak = max(filled.values())
        if peak <= 0:
            return None
        normalized[role] = {factor: value / peak for factor, value in filled.items()}
    return normalized


def _role_from_label(text: str) -> Role | None:
    folded = text.casefold().strip()
    if not folded:
        return None
    if "казнач" in folded:
        return Role.TREASURER
    if "собствен" in folded:
        return Role.OWNER
    if "главбух" in folded or ("главн" in folded and "бухгалтер" in folded):
        return Role.CHIEF_ACCOUNTANT
    if folded == "бухгалтер":
        return Role.CHIEF_ACCOUNTANT
    return None


def _factor_from_label(text: str) -> Factor | None:
    folded = text.casefold().strip()
    if not folded:
        return None
    code = folded.replace(" ", "")
    if code in _FACTOR_CODE:
        return _FACTOR_CODE[code]
    for stem, factor in _FACTOR_STEMS:
        if stem in folded:
            return factor
    return None


def _number(raw: str) -> float | None:
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def _sheet_rows(path: Path, sheet_name: str) -> list[list[str]] | None:
    with zipfile.ZipFile(path) as book:
        names = set(book.namelist())
        target = _sheet_target(book, names, sheet_name)
        if target is None:
            return None
        strings = _shared_strings(book, names)
        root = ET.fromstring(book.read(target))
    return _rows_from_sheet(root, strings)


def workbook_sheet_names(path: Path) -> tuple[str, ...]:
    """Return sheet names. An unreadable file yields an empty tuple."""
    try:
        with zipfile.ZipFile(path) as book:
            workbook = ET.fromstring(book.read("xl/workbook.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError):
        return ()
    names = [
        sheet.attrib.get("name", "")
        for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet")
    ]
    return tuple(name for name in names if name)


def _sheet_target(
    book: zipfile.ZipFile,
    names: set[str],
    sheet_name: str,
) -> str | None:
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    relation_id = None
    for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            relation_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
            break
    if not relation_id:
        return None
    rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall(f".//{{{_PKG_NS}}}Relationship"):
        if rel.attrib.get("Id") != relation_id:
            continue
        target = rel.attrib.get("Target", "").lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        if target in names:
            return target
    return None


def _shared_strings(book: zipfile.ZipFile, names: set[str]) -> list[str]:
    if "xl/sharedStrings.xml" not in names:
        return []
    root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall(f"{{{_MAIN_NS}}}si"):
        parts = [node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")]
        strings.append("".join(parts))
    return strings


def _rows_from_sheet(root: ET.Element, strings: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in root.iter(f"{{{_MAIN_NS}}}row"):
        cells: dict[int, str] = {}
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            ref = cell.attrib.get("r", "")
            cells[_column_index(ref)] = _cell_text(cell, strings)
        if not cells:
            rows.append([])
            continue
        width = max(cells) + 1
        rows.append([cells.get(index, "") for index in range(width)])
    return rows


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        parts = [node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t")]
        return "".join(parts)
    value = cell.find(f"{{{_MAIN_NS}}}v")
    if value is None or value.text is None:
        return ""
    if kind == "s":
        return strings[int(value.text)]
    return value.text


def _column_index(ref: str) -> int:
    letters = "".join(char for char in ref if char.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + ord(char.upper()) - 64
    return max(0, index - 1)
