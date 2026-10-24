"""Serve the Figma screens and the jury checks on one origin.

``demo`` is the default: synthetic companies, the fixed scenario date
and the sample news file. ``live`` re-reads public RSS on a short
cadence. A failed refresh keeps the previous live feed and says so.
The feed list does not call a model. Opening a card calls it once.
The question and the «Ответить» button in that block call it again
through ``/api/card-answer``. ``/api/analysis`` still answers the
field under the card.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Sequence
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

from decision_brief.agent import prepare_analysis
from decision_brief.classify import factors_in_text
from decision_brief.web_api import rate_horizon_present
from decision_brief.conclusion import (
    ModelCallError,
    _CALL_FAILED,
    _UNPARSED,
    build_model_prompt,
    client_from_env,
    reader_model_parts,
)
from decision_brief.demo import DEMO_DATE, SAMPLE_DIR, demo_news
from decision_brief.feeds import dedupe_by_link, parse_rss
from decision_brief.models import CompanyProfile, NewsItem
from decision_brief.roles import Role
from decision_brief.screen import (
    NewsLoad,
    load_demo_companies,
    load_news,
    parsed_feed,
    resolve_companies_path,
    retain_feed,
    rss_failure_message,
    sample_companies_path,
)
from decision_brief.web_api import (
    analysis_view,
    build_feed,
    list_companies,
    list_roles,
    load_payment_rows,
)

_ROOT = Path(__file__).resolve().parents[2]
_WEB = _ROOT / "web"
_PORT = 8780
_RAW_PAYMENTS = _ROOT / "data" / "raw" / "df_Uid_payment_hack.csv"
_DEMO_COMPANY = "U_sample_transport"
_LOCK = threading.Lock()
_COMPANIES: dict[str, list[CompanyProfile]] = {}
_PAYMENTS: dict[str, dict[str, list[dict[str, str]]]] = {}
_LIVE_ITEMS: list[NewsItem] | None = None
_LIVE_NOTICE = ""
_LIVE_AT = ""
_EXTRAS: dict[str, list[NewsItem]] = {"demo": [], "live": []}
_MODEL_CACHE: dict[tuple[str, str, str, str], str] = {}
_ANSWER_CACHE: dict[tuple[str, str, str, str, str], str] = {}
_LIVE_REFRESH_SECONDS = 10
_REFRESH_GUARD = threading.Lock()
_LIVE_THREAD: threading.Thread | None = None

_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def main() -> None:
    """Bind the frontend. One process serves both the pages and the API."""
    _load_local_env()
    _start_live_refresh()
    host, port = _listen()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Frontend http://127.0.0.1:{port}/", flush=True)
    server.serve_forever()


def _listen() -> tuple[str, int]:
    """Address for this process. Local runs stay on localhost."""
    host = os.environ.get("DECISION_BRIEF_BIND", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "0.0.0.0"}:
        host = "127.0.0.1"
    raw_port = os.environ.get("DECISION_BRIEF_WEB_PORT", str(_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = _PORT
    if port < 1 or port > 65535:
        port = _PORT
    return host, port


def _start_live_refresh() -> None:
    """Re-read public RSS while this process is running.

    The first pass waits one interval so a page load can fetch on its
    own. The loop does not overlap its own previous pass. A failed load
    stays in ``_live_items`` and does not replace the previous feed.
    """
    global _LIVE_THREAD
    if _LIVE_THREAD is not None and _LIVE_THREAD.is_alive():
        return
    _LIVE_THREAD = threading.Thread(
        target=_refresh_live_cache,
        name="live-rss",
        daemon=True,
    )
    _LIVE_THREAD.start()


def _refresh_live_cache() -> None:
    """Keep the live snapshot current. This loop does not stop the server."""
    while True:
        time.sleep(_LIVE_REFRESH_SECONDS)
        if not _REFRESH_GUARD.acquire(blocking=False):
            continue
        try:
            _live_items(True)
        except Exception as exc:
            print(f"Live RSS refresh failed: {exc.__class__.__name__}", flush=True)
        finally:
            _REFRESH_GUARD.release()


def combine_live(
    previous: Sequence[NewsItem],
    loaded: NewsLoad,
) -> tuple[list[NewsItem], str]:
    """Keep a live feed when the new RSS load failed.

    Synthetic demo news is never substituted. The notice is empty when
    the load replaced the previous items, including an empty success.
    """
    items, failed = retain_feed(previous, loaded)
    if not failed:
        return list(items), ""
    return list(items), rss_failure_message(kept_previous=bool(previous))


def user_events(payload: dict[str, object], *, as_of: date) -> list[NewsItem]:
    """Parse one manual item or one uploaded RSS document.

    Raises ``ValueError`` with a Russian message the screen can show.
    """
    rss = payload.get("rss")
    if isinstance(rss, str) and rss.strip():
        if len(rss.encode("utf-8")) > 2_000_000:
            raise ValueError("Файл превышает 2 МБ.")
        parsed = parse_rss(rss, "Загруженный RSS")[:100]
        if not parsed:
            raise ValueError(
                "Не найдены элементы с заголовком, HTTP(S)-ссылкой и корректной датой."
            )
        return parsed
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not title or not body:
        raise ValueError("Укажите заголовок и текст события.")
    if len(title) > 300 or len(body) > 4000:
        raise ValueError("Заголовок или текст длиннее допустимого.")
    raw_date = str(payload.get("published") or "").strip()
    try:
        published = date.fromisoformat(raw_date) if raw_date else as_of
    except ValueError as exc:
        raise ValueError("Дата публикации некорректна.") from exc
    url = str(payload.get("url") or "").strip()
    parsed_url = urlsplit(url)
    if url and (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname
        or parsed_url.username
    ):
        raise ValueError("Ссылка должна быть HTTP(S), без учётных данных.")
    identifier = hashlib.sha256((title + body).encode()).hexdigest()[:12]
    return [NewsItem(
        title,
        published,
        "Введено пользователем",
        url or f"https://example.invalid/user-event/{identifier}",
        body,
        factors_in_text(f"{title} {body}"),
    )]


class Handler(BaseHTTPRequestHandler):
    """GET the screens or the JSON feed. POST adds an item or runs analysis."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/bootstrap":
            self._json(200, _bootstrap(_mode(query)))
            return
        if parsed.path == "/api/feed":
            status, payload = _feed(query)
            self._json(status, payload)
            return
        if parsed.path == "/api/card-model":
            status, payload = _card_model(query)
            self._json(status, payload)
            return
        self._file(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._body()
        if payload is None:
            return
        if parsed.path == "/api/events":
            status, answer = _add_event(payload)
            self._json(status, answer)
            return
        if parsed.path == "/api/analysis":
            status, answer = _analysis(payload)
            self._json(status, answer)
            return
        if parsed.path == "/api/card-answer":
            status, answer = _card_answer(payload)
            self._json(status, answer)
            return
        self.send_error(404)

    def _body(self) -> dict[str, object] | None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._json(400, {"error": "Нужен JSON."})
            return None
        if length < 0 or length > 2_000_000:
            self._json(413, {"error": "Файл превышает 2 МБ."})
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._json(400, {"error": "Нужен JSON."})
            return None
        if not isinstance(payload, dict):
            self._json(400, {"error": "Нужен JSON-объект."})
            return None
        return payload

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else unquote(path).lstrip("/")
        target = (_WEB / relative).resolve()
        if not target.is_relative_to(_WEB.resolve()) or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _bootstrap(mode: str) -> dict[str, object]:
    companies = _companies(mode)
    listed = list_companies(companies)
    roles = list_roles()
    preferred = _DEMO_COMPANY if mode == "demo" else ""
    default = preferred if any(row["id"] == preferred for row in listed) else ""
    if not default and listed:
        default = listed[0]["id"]
    return {
        "mode": mode,
        "companies": listed,
        "roles": roles,
        "default_company": default,
        "default_role": roles[0]["id"] if roles else Role.TREASURER.value,
        "as_of": (_scenario_date(mode)).isoformat(),
    }


def _feed(query: dict[str, list[str]]) -> tuple[int, dict[str, object]]:
    mode = _mode(query)
    company, role, error = _selection(mode, query)
    if error is not None:
        return error
    try:
        items, notice, loaded_at = _items(mode, _first(query, "refresh") == "1")
    except OSError:
        return 502, {"error": "Лента не прочиталась."}
    companies_path, payments_path = _paths(mode)
    payments = _payment_index(payments_path).get(company.synthetic_u, [])
    payload = build_feed(
        company,
        items,
        role,
        as_of=_scenario_date(mode),
        source=mode,
        notice=notice,
        loaded_at=loaded_at,
        payments=payments,
    )
    payload["companies_note"] = str(companies_path.name)
    return 200, payload


def _add_event(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    mode = _mode_value(payload.get("mode"))
    try:
        created = user_events(payload, as_of=_scenario_date(mode))
    except ValueError as exc:
        return 400, {"error": str(exc)}
    with _LOCK:
        _EXTRAS[mode] = dedupe_by_link(_EXTRAS[mode] + created)[-100:]
    return 200, {"added": len(created)}


def _card_model(query: dict[str, list[str]]) -> tuple[int, dict[str, object]]:
    """One model block for the card the user opened. The list is not scored here."""
    mode = _mode(query)
    company, role, error = _selection(mode, query)
    if error is not None:
        return error
    item_id = _first(query, "item")
    if not item_id:
        return 400, {"error": "Нужна карточка события."}
    cache_key = (mode, company.synthetic_u, role.value, item_id)
    with _LOCK:
        cached = _MODEL_CACHE.get(cache_key, "")
    if cached:
        return 200, _cached_model(cached)
    try:
        items, _notice, _loaded = _items(mode, refresh=False)
    except OSError:
        return 502, {"error": "Лента не прочиталась."}
    scored = parsed_feed(company, items, role, as_of=_scenario_date(mode))
    match = next((row for row in scored if row.item.source_url == item_id), None)
    if match is None:
        return 404, {"error": "Событие не найдено в ленте."}
    client = client_from_env()
    if client is None:
        return 200, {
            "model": "",
            "status": "unavailable",
            "error": "Шлюз не настроен: нет модели, адреса или ключа.",
        }
    prompt = build_model_prompt(company, match, role=role)
    try:
        parts = reader_model_parts(client.complete(prompt), prompt)
        parts["summary"] = _settle_shown_text(str(parts.get("summary", "")), match)
        parts["headline"] = _settle_shown_text(str(parts.get("headline", "")), match)
        if rate_horizon_present(match):
            parts["next"] = ""
    except ModelCallError:
        return 200, {"model": "", "status": "failed", "error": "Вызов модели не выполнен."}
    packed = json.dumps(parts, ensure_ascii=False)
    if parts["summary"] not in {"", _UNPARSED, _CALL_FAILED}:
        with _LOCK:
            _MODEL_CACHE[cache_key] = packed
    return 200, _model_body(parts, "ready")


_STALE_PAUSE = re.compile(
    r"Банк ожидает паузу[^.]*?23 октября",
    re.IGNORECASE,
)
_BANK_ECHO = re.compile(r"7,5.*87,2|87,2.*7,5")


def _settle_shown_text(text: str, scored: object) -> str:
    """A passed decision is not still expected, and bank figures stay in block 04."""
    item = getattr(scored, "item", None)
    published = getattr(item, "published_on", None)
    if not text or published is None or published < date(2026, 10, 23):
        return text
    settled = _STALE_PAUSE.sub("Пауза 23 октября уже состоялась", text)
    settled = settled.replace("уже состоялась и ", "уже состоялась, а ")
    kept: list[str] = []
    for sentence in re.split(r"(?<=\.)\s+", settled.strip()):
        if _BANK_ECHO.search(sentence) and not re.search(
            r"кредит|лизинг|закуп|бизнес",
            sentence,
            re.IGNORECASE,
        ):
            continue
        if sentence:
            kept.append(sentence if sentence.endswith(".") else f"{sentence}.")
    return " ".join(kept)


def _card_answer(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    """One model answer to the question already shown in block 05."""
    mode = _mode_value(payload.get("mode"))
    query = {
        "company": [str(payload.get("company") or "")],
        "role": [str(payload.get("role") or "")],
        "item": [str(payload.get("item") or "")],
    }
    company, role, error = _selection(mode, query)
    if error is not None:
        return error
    item_id = str(payload.get("item") or "")
    asked = " ".join(str(payload.get("question") or "").split())[:500]
    if not item_id or not asked:
        return 400, {"error": "Нужны событие и вопрос."}
    cache_key = (mode, company.synthetic_u, role.value, item_id, asked)
    with _LOCK:
        cached = _ANSWER_CACHE.get(cache_key, "")
    if cached:
        return 200, {"answer": cached, "status": "cached"}
    try:
        items, _notice, _loaded = _items(mode, refresh=False)
    except OSError:
        return 502, {"error": "Лента не прочиталась."}
    scored = parsed_feed(company, items, role, as_of=_scenario_date(mode))
    match = next((row for row in scored if row.item.source_url == item_id), None)
    if match is None:
        return 404, {"error": "Событие не найдено в ленте."}
    client = client_from_env()
    if client is None:
        return 200, {"answer": "", "status": "unavailable", "error": "Шлюз не настроен."}
    prompt = build_model_prompt(company, match, role=role) + (
        "\nОтветь на вопрос клиента. Добавь в JSON ключ «ответ»: "
        "одно или два коротких предложения по полям выше. "
        "Если данных нет, так и напиши. Слово «почему» не пиши.\n"
        f"Вопрос: {asked}"
    )
    try:
        parts = reader_model_parts(client.complete(prompt), prompt)
    except ModelCallError:
        return 200, {"answer": "", "status": "failed", "error": "Вызов модели не выполнен."}
    answer = _settle_shown_text(parts.get("answer", ""), match)
    if not answer:
        return 200, {"answer": "", "status": "empty", "error": "Модель не ответила на вопрос."}
    with _LOCK:
        _ANSWER_CACHE[cache_key] = answer
    return 200, {"answer": answer, "status": "ready"}


def _cached_model(cached: str) -> dict[str, object]:
    """Restore a stored card. Older cache rows are a single paragraph."""
    try:
        payload = json.loads(cached)
    except json.JSONDecodeError:
        payload = {"summary": cached}
    if not isinstance(payload, dict):
        payload = {"summary": cached}
    return _model_body(payload, "cached")


def _model_body(parts: dict[str, object], status: str) -> dict[str, object]:
    """Summary for block 05 and short lines for the consequence columns."""
    def text(key: str) -> str:
        value = parts.get(key, "")
        return value.strip() if isinstance(value, str) else ""

    return {
        "model": text("summary"),
        "headline": text("headline"),
        "question": text("question"),
        "effects": {
            "risk": text("risk"),
            "opportunity": text("opportunity"),
            "next": text("next"),
            "gaps": text("gaps"),
        },
        "status": status,
    }


def _analysis(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    mode = _mode_value(payload.get("mode"))
    query = {
        "company": [str(payload.get("company") or "")],
        "role": [str(payload.get("role") or "")],
    }
    company, role, error = _selection(mode, query)
    if error is not None:
        return error
    try:
        items, _notice, _loaded = _items(mode, refresh=False)
    except OSError:
        return 502, {"error": "Лента не прочиталась."}
    companies_path, payments_path = _paths(mode)
    result = prepare_analysis(
        company,
        items,
        role,
        as_of=_scenario_date(mode),
        client=client_from_env(),
        question=str(payload.get("question") or ""),
        companies_path=companies_path,
        payments_path=payments_path,
    )
    return 200, analysis_view(result)


def _selection(
    mode: str,
    query: dict[str, list[str]],
) -> tuple[CompanyProfile, Role, tuple[int, dict[str, object]] | None]:
    companies = _companies(mode)
    by_id = {company.synthetic_u: company for company in companies}
    catalog = _bootstrap(mode)
    company_id = _first(query, "company") or str(catalog["default_company"])
    role_id = _first(query, "role") or str(catalog["default_role"])
    company = by_id.get(company_id)
    if company is None:
        return (
            CompanyProfile(synthetic_u=""),
            Role.TREASURER,
            (404, {"error": "Компания не найдена в файле."}),
        )
    try:
        role = Role(role_id)
    except ValueError:
        return company, Role.TREASURER, (400, {"error": "Такой роли в ранжировании нет."})
    return company, role, None


def _items(mode: str, refresh: bool) -> tuple[list[NewsItem], str, str]:
    if mode == "demo":
        base = list(demo_news())
        notice = f"Синтетические события. Дата сценария {DEMO_DATE:%d.%m.%Y}."
        loaded_at = DEMO_DATE.strftime("%d.%m.%Y")
    else:
        base, notice, loaded_at = _live_items(refresh)
    with _LOCK:
        extras = list(_EXTRAS[mode])
    return dedupe_by_link(base + extras), notice, loaded_at


def _live_items(refresh: bool) -> tuple[list[NewsItem], str, str]:
    global _LIVE_ITEMS, _LIVE_NOTICE, _LIVE_AT
    with _LOCK:
        previous = list(_LIVE_ITEMS) if _LIVE_ITEMS is not None else []
        if not refresh and _LIVE_ITEMS is not None:
            return previous, _LIVE_NOTICE, _LIVE_AT
    loaded = load_news()
    items, notice = combine_live(previous, loaded)
    loaded_at = datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
    with _LOCK:
        _LIVE_ITEMS = items
        _LIVE_NOTICE = notice
        _LIVE_AT = loaded_at
    return items, notice, loaded_at


def _companies(mode: str) -> list[CompanyProfile]:
    with _LOCK:
        cached = _COMPANIES.get(mode)
        if cached is None:
            path, _payments = _paths(mode)
            cached = load_demo_companies(path)
            _COMPANIES[mode] = cached
        return list(cached)


def _paths(mode: str) -> tuple[Path, Path | None]:
    if mode == "demo":
        return sample_companies_path(), SAMPLE_DIR / "payments.csv"
    companies = resolve_companies_path()
    override = os.environ.get("DECISION_BRIEF_PAYMENTS", "").strip()
    if override:
        return companies, Path(override)
    if companies.resolve() == sample_companies_path().resolve():
        return companies, SAMPLE_DIR / "payments.csv"
    if _RAW_PAYMENTS.is_file():
        return companies, _RAW_PAYMENTS
    return companies, None


def _payment_index(path: Path | None) -> dict[str, list[dict[str, str]]]:
    if path is None or not path.is_file():
        return {}
    key = str(path.resolve())
    with _LOCK:
        cached = _PAYMENTS.get(key)
        if cached is None:
            cached = load_payment_rows(path)
            _PAYMENTS[key] = cached
        return cached


def _scenario_date(mode: str) -> date:
    return DEMO_DATE if mode == "demo" else date.today()


def _mode(query: dict[str, list[str]]) -> str:
    return _mode_value(_first(query, "mode"))


def _mode_value(value: object) -> str:
    return "live" if str(value or "").strip() == "live" else "demo"


def _load_local_env() -> None:
    """Fill missing settings from the gitignored .env. Never override the process."""
    path = _ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("DECISION_BRIEF_") and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return values[0].strip() if values else ""


if __name__ == "__main__":
    main()
