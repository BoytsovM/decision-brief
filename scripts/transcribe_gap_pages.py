"""One offline transcription pass over the bank PDFs with blank pages.

Not imported by the screen, the feed, or the text-model client. The
gateway URL and key come from the environment. The vision model name is
fixed for this pass and is not taken from ``DECISION_BRIEF_MODEL``, so
the text client keeps refusing that name.

Run from the repository root:

    python scripts/transcribe_gap_pages.py
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from PIL import Image
from pypdf import PdfReader

from decision_brief.chart_draft import (
    UNVERIFIED,
    ChartDraft,
    ChartReading,
    default_draft_path,
    gap_page_targets,
    parse_transcription,
    pdf_name_matches,
    save_draft,
    transcription_prompt,
)
from decision_brief.conclusion import chat_completions_url

_MODEL = "Qwen3-VL-30B-A3B-Instruct"
_URL_ENV = "DECISION_BRIEF_BASE_URL"
_KEY_ENV = "DECISION_BRIEF_API_KEY"


def main(argv: list[str] | None = None) -> int:
    """Transcribe gap-list pages, or write an empty unverified draft.

    Chart numbers are written only when the gateway answers. They are
    not printed and not copied onto bank cards.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    directories = [_ROOT / "data" / "raw"]
    directories.extend(Path(item) for item in args)
    gateway = _gateway()
    rows: list[ChartReading] = []
    missing: list[str] = []
    notes: list[str] = []
    opened: list[str] = []
    if gateway is None:
        notes.append(
            "Вызов не выполнен: нет DECISION_BRIEF_BASE_URL или "
            "DECISION_BRIEF_API_KEY. Числа с графиков не записывались."
        )
    for target in gap_page_targets():
        path = _find_pdf(directories, target.filename)
        if path is None:
            missing.append(target.card_id)
            notes.append(f"{target.card_id}: файл {target.filename} не найден.")
            continue
        page_count = _page_count(path)
        if page_count is None:
            notes.append(f"{target.card_id}: страницы файла не прочитаны.")
            continue
        opened.append(f"{target.card_id} {path.name} страниц {page_count}")
        if gateway is None:
            continue
        base_url, api_key = gateway
        for page_number in range(1, page_count + 1):
            try:
                png = _page_png(path, page_number - 1)
                raw = _vision_complete(
                    base_url=base_url,
                    api_key=api_key,
                    png=png,
                    prompt=transcription_prompt(page_number),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                notes.append(
                    f"{target.card_id} стр. {page_number}: {exc.__class__.__name__}."
                )
                continue
            rows.extend(
                parse_transcription(
                    raw,
                    card_id=target.card_id,
                    filename=path.name,
                    card_filename=target.filename,
                    pdf_page=page_number,
                )
            )
            _write(rows, missing, notes, opened)
    if gateway is not None:
        notes.append(
            "Один офлайн-проход. Числа не проверены и в ответ пользователю "
            "не подставляются."
        )
    _write(rows, missing, notes, opened)
    print(
        f"draft {default_draft_path().name} rows {len(rows)} "
        f"missing {len(missing)} status {UNVERIFIED}"
    )
    return 0


def _write(
    rows: list[ChartReading],
    missing: list[str],
    notes: list[str],
    opened: list[str],
) -> None:
    note = " ".join(notes)
    if opened:
        note = f"{note} Файлы: {'; '.join(opened)}."
    draft = ChartDraft(
        status=UNVERIFIED,
        model=_MODEL,
        note=note.strip(),
        missing=tuple(missing),
        rows=tuple(rows),
    )
    save_draft(default_draft_path(), draft)


def _gateway() -> tuple[str, str] | None:
    base_url = os.environ.get(_URL_ENV, "").strip()
    api_key = os.environ.get(_KEY_ENV, "").strip()
    if not base_url or not api_key:
        return None
    if not base_url.lower().startswith(("http://", "https://")):
        return None
    return base_url, api_key


def _find_pdf(directories: list[Path], filename: str) -> Path | None:
    exact: list[Path] = []
    loose: list[Path] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.glob("*.pdf"):
            if path.name.casefold() == Path(filename).name.casefold():
                exact.append(path)
            elif pdf_name_matches(filename, path.name):
                loose.append(path)
    if exact:
        return exact[0]
    if not loose:
        return None
    return min(loose, key=lambda path: len(path.name))


def _page_count(path: Path) -> int | None:
    try:
        return len(PdfReader(str(path)).pages)
    except (OSError, ValueError):
        return None


def _page_png(path: Path, page_index: int) -> bytes:
    reader = PdfReader(str(path))
    page = reader.pages[page_index]
    resources = page.get("/Resources")
    if resources is None:
        raise RuntimeError("page has no resources")
    xobject = resources.get_object().get("/XObject")
    if xobject is None:
        raise RuntimeError("page has no image")
    best_area = -1
    best: object | None = None
    for ref in xobject.get_object().values():
        image = ref.get_object()
        if image.get("/Subtype") != "/Image":
            continue
        area = int(image.get("/Width")) * int(image.get("/Height"))
        if area > best_area:
            best = image
            best_area = area
    if best is None:
        raise RuntimeError("page has no image")
    width = int(best.get("/Width"))
    height = int(best.get("/Height"))
    raw = best.get_data()
    mode = _image_mode(len(raw), width, height)
    picture = Image.frombytes(mode, (width, height), raw)
    if picture.mode != "RGB":
        picture = picture.convert("RGB")
    picture.thumbnail((1400, 1800), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return buffer.getvalue()


def _image_mode(size: int, width: int, height: int) -> str:
    pixels = width * height
    if size == pixels * 3:
        return "RGB"
    if size == pixels:
        return "L"
    if size == pixels * 4:
        return "RGBA"
    raise RuntimeError(f"unexpected image size {size} for {width}x{height}")


def _vision_complete(
    *,
    base_url: str,
    api_key: str,
    png: bytes,
    prompt: str,
) -> str:
    """POST one page. The error text does not include the key."""
    encoded = base64.b64encode(png).decode("ascii")
    body = json.dumps(
        {
            "model": _MODEL,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encoded}",
                            },
                        },
                    ],
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        chat_completions_url(base_url),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError("The model gateway did not answer.") from exc
    return _content_text(raw)


def _content_text(raw: str) -> str:
    try:
        payload = json.loads(raw)
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The model gateway returned an unreadable body.") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    raise RuntimeError("The model gateway returned an unreadable body.")


if __name__ == "__main__":
    raise SystemExit(main())
