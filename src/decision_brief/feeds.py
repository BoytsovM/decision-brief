"""Turn an RSS document into news items. Network access stays outside tests."""

from __future__ import annotations

import re
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from decision_brief.classify import factors_in_text
from decision_brief.models import NewsItem

# The six public feeds. Tests never open them; ``fetch_rss`` does.
FEED_URLS: tuple[str, ...] = (
    "https://www.gazeta.ru/export/rss/business.xml",
    "https://www.interfax.ru/rss",
    "https://www.cbr.ru/rss/eventrss",
    "https://www.vedomosti.ru/rss/rubric/finance/banks",
    "http://www.cbr.ru/rss/RssPress",
    "https://www.cbr.ru/rss/RssCurrency",
)

_SOURCE_BY_HOST: dict[str, str] = {
    "gazeta.ru": "Газета.Ru",
    "interfax.ru": "Интерфакс",
    "cbr.ru": "Банк России",
    "vedomosti.ru": "Ведомости",
}

_ENCODING_RE = re.compile(
    br"""encoding\s*=\s*['"]([A-Za-z0-9_.-]+)['"]""",
    re.IGNORECASE,
)


def parse_rss(xml_text: str, source_name: str) -> list[NewsItem]:
    """Parse an RSS 2.0 string. Items without a title or a link are skipped."""
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for node in root.iter("item"):
        title = _text(node, "title")
        link = _text(node, "link")
        if not title or not link:
            continue
        summary = _text(node, "description")
        published = _published_on(_text(node, "pubDate"))
        body = f"{title}. {summary}".strip()
        items.append(
            NewsItem(
                title=title,
                published_on=published,
                source_name=source_name,
                source_url=link,
                summary=summary,
                factors=factors_in_text(body),
            )
        )
    return items


def _text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _published_on(raw: str) -> date:
    if not raw:
        return date.today()
    try:
        parsed: datetime = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return date.today()
    return parsed.date()


def fetch_rss(url: str, timeout: float = 30.0) -> str:
    """Download one feed as text. This is the only network call."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "decision-brief/0.1"},
    )
    with _open_url(request, timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset()
    return decode_rss(raw, charset)


def decode_rss(raw: bytes, charset: str | None = None) -> str:
    """Turn feed bytes into text.

    The XML declaration wins over the HTTP charset. A leading BOM is
    dropped so it does not sit in front of the declaration.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    encoding = _declared_encoding(raw) or charset or "utf-8"
    try:
        return raw.decode(encoding)
    except (LookupError, UnicodeError):
        return raw.decode("utf-8", errors="replace")


def dedupe_by_link(items: list[NewsItem]) -> list[NewsItem]:
    """Keep the first item for each link and drop later copies."""
    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in items:
        link = item.source_url.strip()
        if not link or link in seen:
            continue
        seen.add(link)
        unique.append(item)
    return unique


def load_feeds(
    urls: Sequence[str] = FEED_URLS,
    *,
    fetcher: Callable[[str], str] = fetch_rss,
) -> list[NewsItem]:
    """Read every address through ``parse_rss`` and collapse duplicate links.

    One failed address does not stop the others. Scores on the returned
    items still come from ``factors_in_text`` (every hit is 3). Graded
    strength is ``grade_text`` and is not applied here.
    """
    collected: list[NewsItem] = []
    for url in urls:
        try:
            xml_text = fetcher(url)
            collected.extend(parse_rss(xml_text, _source_name(url)))
        except (OSError, ET.ParseError, UnicodeError, ValueError):
            continue
    return dedupe_by_link(collected)


def source_name_for(url: str) -> str:
    """Display name of a feed URL. An unknown host is shown as the host."""
    return _source_name(url)


def _declared_encoding(raw: bytes) -> str | None:
    match = _ENCODING_RE.search(raw[:400])
    if match is None:
        return None
    return match.group(1).decode("ascii", errors="ignore") or None


def _source_name(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return _SOURCE_BY_HOST.get(host, host)


def _open_url(request: urllib.request.Request, timeout: float):
    """Open ``request``, and retry CBR once if the local trust store fails."""
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        if not isinstance(getattr(exc, "reason", None), ssl.SSLError):
            raise
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(request, timeout=timeout, context=context)
