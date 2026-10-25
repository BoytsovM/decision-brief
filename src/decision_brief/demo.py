"""Reproducible, explicitly synthetic data; never requires a network call."""

from datetime import date
from pathlib import Path

from decision_brief.feeds import parse_rss

DEMO_DATE = date(2026, 10, 21)
SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"


def demo_news():
    return parse_rss((SAMPLE_DIR / "news.xml").read_text(encoding="utf-8"),
                     "Синтетические события для проверки")
