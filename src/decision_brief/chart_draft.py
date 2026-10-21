"""Unverified chart transcription stored beside the bank cards.

This is not ``BANK_CARDS`` and it is not shown to the user. Nothing here
opens a PDF or calls a model. The one-off pass lives in
``scripts/transcribe_gap_pages.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from decision_brief.bank_cards import BANK_CARDS, cards_missing_page

UNVERIFIED = "не проверено"

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_FIELDS = (
    ("страница", "page"),
    ("название графика", "chart_title"),
    ("ряд", "series"),
    ("число", "number"),
    ("единица", "unit"),
    ("дата", "observed_on"),
)


@dataclass(frozen=True)
class GapTarget:
    """One card whose PDF page is still blank."""

    card_id: str
    filename: str


@dataclass(frozen=True)
class ChartReading:
    """One number taken from a chart. It is not a bank thesis."""

    card_id: str
    filename: str
    card_filename: str
    pdf_page: str
    page: str
    chart_title: str
    series: str
    number: str
    unit: str
    observed_on: str
    status: str


@dataclass(frozen=True)
class ChartDraft:
    """A transcription file. ``status`` stays unverified."""

    status: str
    model: str
    note: str
    missing: tuple[str, ...]
    rows: tuple[ChartReading, ...]


def default_draft_path() -> Path:
    """JSON draft next to the bank-card module. It is not ``BANK_CARDS``."""
    return Path(__file__).resolve().parent / "chart_transcription_draft.json"


def transcription_prompt(page_number: int) -> str:
    """Ask for page, chart title, series, number, unit, and date.

    The bank's opinion is not requested.
    """
    return (
        "Транскрибируй графики на этой странице PDF. "
        f"Номер страницы в файле: {page_number}. "
        "Верни только JSON-массив. "
        "Каждый элемент — одно число одного ряда и содержит поля "
        "«страница», «название графика», «ряд», «число», «единица», «дата». "
        "Число запиши строкой, как оно напечатано. "
        "Если графика нет, верни пустой массив. "
        "Мнение банка не добавляй."
    )


def gap_page_targets() -> tuple[GapTarget, ...]:
    """Card ids whose page is still empty, with the filename on the card.

    Reading the gap list does not write a page number back onto a card.
    """
    names = {card.card_id: card.filename for card in BANK_CARDS}
    return tuple(
        GapTarget(card_id=card_id, filename=names[card_id])
        for card_id in cards_missing_page()
    )


def pdf_name_matches(card_filename: str, found_name: str) -> bool:
    """True when ``found_name`` is the card file or a longer scan of it.

    Cyrillic and Latin ``k`` match. The 2021 steel file on disk is longer
    than the name stored on the card.
    """
    if Path(card_filename).name.casefold() == Path(found_name).name.casefold():
        return True
    stem = _fold_name(Path(card_filename).stem)
    found = _fold_name(Path(found_name).stem)
    return bool(stem) and stem in found


def parse_transcription(
    raw: str,
    *,
    card_id: str,
    filename: str,
    card_filename: str,
    pdf_page: int,
) -> tuple[ChartReading, ...]:
    """Parse a JSON array of chart numbers. Every row is unverified.

    A value that is not JSON, and a row with an empty number, are dropped.
    The caller-supplied PDF page is kept even when the model leaves
    «страница» blank. A status written by the model is not kept.
    """
    payload = _load_array(raw)
    if payload is None:
        return ()
    rows: list[ChartReading] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        fields = {name: _text_field(item, key) for key, name in _FIELDS}
        if not fields["number"]:
            continue
        rows.append(
            ChartReading(
                card_id=card_id,
                filename=filename,
                card_filename=card_filename,
                pdf_page=str(pdf_page),
                page=fields["page"],
                chart_title=fields["chart_title"],
                series=fields["series"],
                number=fields["number"],
                unit=fields["unit"],
                observed_on=fields["observed_on"],
                status=UNVERIFIED,
            )
        )
    return tuple(rows)


def empty_draft(
    *,
    model: str,
    note: str,
    missing: tuple[str, ...] = (),
) -> ChartDraft:
    """Draft with no chart numbers. The status is unverified."""
    return ChartDraft(
        status=UNVERIFIED,
        model=model,
        note=note,
        missing=missing,
        rows=(),
    )


def readings_for_user_response(draft: ChartDraft) -> tuple[str, ...]:
    """Return no numbers. The draft is not copied into the user answer."""
    if draft.status:
        return ()
    return ()


def save_draft(path: Path, draft: ChartDraft) -> None:
    """Write the draft. Status on the file and on every row is unverified."""
    payload = {
        "status": UNVERIFIED,
        "model": draft.model,
        "note": draft.note,
        "missing": list(draft.missing),
        "rows": [_row_payload(row) for row in draft.rows],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_draft(path: Path) -> ChartDraft:
    """Read a draft and mark it unverified again.

    A file that says the readings were checked is still unverified.
    Empty numbers are left out. Bank cards are not updated.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[ChartReading] = []
    raw_rows = payload.get("rows", [])
    if isinstance(raw_rows, list):
        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            number = _stored_text(item, "number")
            if not number:
                continue
            rows.append(
                ChartReading(
                    card_id=_stored_text(item, "card_id"),
                    filename=_stored_text(item, "filename"),
                    card_filename=_stored_text(item, "card_filename"),
                    pdf_page=_stored_text(item, "pdf_page"),
                    page=_stored_text(item, "page"),
                    chart_title=_stored_text(item, "chart_title"),
                    series=_stored_text(item, "series"),
                    number=number,
                    unit=_stored_text(item, "unit"),
                    observed_on=_stored_text(item, "observed_on"),
                    status=UNVERIFIED,
                )
            )
    missing_raw = payload.get("missing", [])
    missing = (
        tuple(str(item) for item in missing_raw)
        if isinstance(missing_raw, list)
        else ()
    )
    return ChartDraft(
        status=UNVERIFIED,
        model=_stored_text(payload, "model") if isinstance(payload, dict) else "",
        note=_stored_text(payload, "note") if isinstance(payload, dict) else "",
        missing=missing,
        rows=tuple(rows),
    )


def _fold_name(name: str) -> str:
    return name.casefold().replace("к", "k")


def _load_array(raw: str) -> list[object] | None:
    text = _FENCE.sub("", raw.strip()).strip()
    parsed = _as_list(text)
    if parsed is not None:
        return parsed
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return None
    return _as_list(text[start : end + 1])


def _as_list(text: str) -> list[object] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, list):
        return payload
    return None


def _text_field(row: dict[str, object], key: str) -> str:
    value = row.get(key, "")
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, float):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return ""


def _stored_text(row: dict[str, object], key: str) -> str:
    value = row.get(key, "")
    if isinstance(value, str):
        return value.strip()
    return ""


def _row_payload(row: ChartReading) -> dict[str, str]:
    return {
        "card_id": row.card_id,
        "filename": row.filename,
        "card_filename": row.card_filename,
        "pdf_page": row.pdf_page,
        "page": row.page,
        "chart_title": row.chart_title,
        "series": row.series,
        "number": row.number,
        "unit": row.unit,
        "observed_on": row.observed_on,
        "status": UNVERIFIED,
    }
