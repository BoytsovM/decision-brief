"""Saved RSS items and the offline feed loader. No network."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from decision_brief.classify import (
    factors_in_text,
    grade_text,
    mark_industry,
    payment_ruble,
)
from decision_brief.feeds import FEED_URLS, decode_rss, dedupe_by_link, load_feeds, parse_rss
from decision_brief.models import CompanyProfile, Factor, NewsItem
from decision_brief.scoring import score_item

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "rss"
_AS_OF = date(2026, 10, 21)
_EMPTY_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel></channel></rss>
"""


def _one(name: str) -> NewsItem:
    xml_text = (_FIXTURES / name).read_text(encoding="utf-8")
    items = parse_rss(xml_text, "fixture")
    if len(items) != 1:
        raise AssertionError(f"{name} parsed {len(items)} items")
    return items[0]


class SavedPublicationTest(unittest.TestCase):
    def test_gazeta_credit_item_is_graded_from_the_body(self) -> None:
        item = _one("gazeta_rate_credit.xml")
        self.assertEqual(
            item.source_url,
            "https://www.gazeta.ru/business/news/2026/10/20/29561401.shtml",
        )
        self.assertEqual(item.published_on, date(2026, 10, 20))
        graded = grade_text(item.title, item.summary, industry="finance")
        self.assertEqual(graded.credit, 2)
        self.assertEqual(graded.deposit, 2)
        self.assertFalse(graded.mentions_industry)
        legacy = factors_in_text(f"{item.title}. {item.summary}")
        self.assertEqual(legacy[Factor.RATE], 3)
        self.assertEqual(graded.factors[Factor.BUDGET], 1)
        self.assertEqual(legacy[Factor.BUDGET], 3)

    def test_interfax_deposit_item_does_not_become_credit(self) -> None:
        item = _one("interfax_deposit_tax.xml")
        self.assertEqual(item.source_url, "https://www.interfax.ru/business/1119596")
        self.assertEqual(item.published_on, date(2026, 10, 1))
        graded = grade_text(item.title, item.summary, industry="finance")
        self.assertEqual(graded.deposit, 3)
        self.assertEqual(graded.credit, 0)
        self.assertFalse(graded.mentions_industry)

    def test_cbr_item_names_credit_and_deposit(self) -> None:
        item = _one("cbr_rate_dynamics.xml")
        self.assertEqual(item.source_url, "https://www.cbr.ru/press/event/?id=32903")
        self.assertEqual(item.published_on, date(2026, 10, 9))
        graded = grade_text(item.title, item.summary, industry="transport")
        self.assertEqual(graded.credit, 3)
        self.assertEqual(graded.deposit, 1)
        self.assertFalse(graded.mentions_industry)


class GradeScaleTest(unittest.TestCase):
    def test_title_is_three_and_one_body_hit_is_one(self) -> None:
        self.assertEqual(grade_text("Инфляция выросла", "").factors[Factor.INFLATION], 3)
        body_only = grade_text("Обзор", "Инфляция замедлилась")
        self.assertEqual(body_only.factors[Factor.INFLATION], 1)
        self.assertEqual(factors_in_text("Обзор. Инфляция замедлилась")[Factor.INFLATION], 3)

    def test_repeated_body_hit_is_two(self) -> None:
        graded = grade_text("Обзор", "Инфляция высокая, и снова инфляция")
        self.assertEqual(graded.factors[Factor.INFLATION], 2)

    def test_direct_industry_name_is_a_separate_flag(self) -> None:
        named = grade_text(
            "Транспортные компании подняли тарифы",
            "",
            industry="transport",
        )
        self.assertTrue(named.mentions_industry)
        central_bank = grade_text(
            "Банк России сохранил ставку",
            "",
            industry="finance",
        )
        self.assertFalse(central_bank.mentions_industry)
        sector = grade_text("Банковский сектор получил прибыль", "", industry="finance")
        self.assertTrue(sector.mentions_industry)
        not_it = grade_text("Компании хотят найти подрядчика", "", industry="it")
        self.assertFalse(not_it.mentions_industry)
        it_sector = grade_text("IT-отрасль ждёт кадры", "", industry="it")
        self.assertTrue(it_sector.mentions_industry)
        self.assertFalse(grade_text("Обзор экономики", "", industry="infrastructure").mentions_industry)

    def test_industry_flag_reaches_the_existing_score(self) -> None:
        company = CompanyProfile(synthetic_u="t", industry="transport")
        item = NewsItem(
            title="Транспортные компании и ключевая ставка",
            published_on=date(2026, 10, 20),
            source_name="fixture",
            source_url="https://example.test/transport",
            factors=factors_in_text("Транспортные компании и ключевая ставка"),
        )
        plain, _ = score_item(company, item, as_of=_AS_OF)
        marked = mark_industry(item, "transport")
        bumped, reasons = score_item(company, marked, as_of=_AS_OF)
        self.assertGreater(bumped, plain)
        self.assertTrue(marked.mentions_industry)
        self.assertTrue(any("отрасль" in reason for reason in reasons))


class FeedLoaderTest(unittest.TestCase):
    def test_loader_walks_every_address_without_stopping(self) -> None:
        seen: list[str] = []

        def fake(url: str) -> str:
            seen.append(url)
            if url.endswith("RssCurrency"):
                raise TimeoutError("slow")
            link = "https://example.test/same" if "cbr.ru" in url else url
            return _item(link, "Ключевая ставка")

        items = load_feeds(fetcher=fake)
        self.assertEqual(seen, list(FEED_URLS))
        self.assertEqual(len(FEED_URLS), 6)
        cbr = [item for item in items if item.source_url == "https://example.test/same"]
        self.assertEqual(len(cbr), 1)
        self.assertEqual(cbr[0].source_name, "Банк России")
        self.assertEqual(cbr[0].factors[Factor.RATE], 3)

    def test_duplicate_links_keep_the_first_item(self) -> None:
        first = _news("https://example.test/a", "one")
        second = _news("https://example.test/a", "two")
        other = _news("https://example.test/b", "three")
        kept = dedupe_by_link([first, second, other])
        self.assertEqual([item.source_name for item in kept], ["one", "three"])

    def test_windows1251_declaration_decodes_to_text(self) -> None:
        raw = (
            '<?xml version="1.0" encoding="windows-1251"?>'
            "<rss><channel><title>Ставка</title></channel></rss>"
        ).encode("cp1251")
        self.assertIn("Ставка", decode_rss(raw))

    def test_bom_is_not_left_in_front_of_the_declaration(self) -> None:
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<rss><channel><title>Ставка</title></channel></rss>"
        )
        text = decode_rss(b"\xef\xbb\xbf" + body.encode("utf-8"))
        self.assertTrue(text.startswith("<?xml"))
        self.assertNotIn("\ufeff", text)

    def test_broken_document_does_not_stop_later_feeds(self) -> None:
        seen: list[str] = []

        def fake(url: str) -> str:
            seen.append(url)
            if "vedomosti" in url:
                return "<not-rss"
            return _item(url, "Курс доллара")

        items = load_feeds(fetcher=fake)
        self.assertEqual(seen, list(FEED_URLS))
        self.assertEqual(len(items), 5)
        self.assertTrue(all(item.factors.get(Factor.FX) == 3 for item in items))

    def test_digital_ruble_is_not_a_currency_factor(self) -> None:
        graded = grade_text(
            "Бизнес назвал препятствия для внедрения цифрового рубля",
            "Закон о цифровом рубле. Сумма 1 трлн рублей в обороте.",
        )
        self.assertEqual(graded.factors.get(Factor.FX, 0), 0)
        self.assertFalse(payment_ruble("курс рубля"))
        self.assertEqual(
            factors_in_text("Курс рубля обновил минимум")[Factor.FX],
            3,
        )
        mortgage = grade_text(
            "ЦБ уточнил расчеты ставки по семейной ипотеке",
            "Потолок по семейной ипотеке.",
        )
        self.assertEqual(mortgage.factors.get(Factor.RATE), 3)
        self.assertEqual(mortgage.factors.get(Factor.FX, 0), 0)


def _item(link: str, title: str) -> str:
    return f"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>{title}</title>
        <link>{link}</link>
        <pubDate>Tue, 20 Oct 2026 06:00:00 +0300</pubDate>
        <description>Коротко.</description>
      </item>
    </channel></rss>
    """


def _news(link: str, source_name: str) -> NewsItem:
    return NewsItem(
        title="t",
        published_on=date(2026, 10, 20),
        source_name=source_name,
        source_url=link,
    )


if __name__ == "__main__":
    unittest.main()
