"""Checks for the filter, RSS parsing, and stale bank notes."""

from __future__ import annotations

import unittest
from datetime import date

from decision_brief.bank_cards import latest_card_for
from decision_brief.classify import factors_in_text
from decision_brief.feeds import parse_rss
from decision_brief.models import CompanyProfile, Factor, NewsItem, Relevance
from decision_brief.pipeline import rank_for_company
from decision_brief.scoring import exposure, relevance_for, score_item

_AS_OF = date(2026, 10, 21)


def _rate_item() -> NewsItem:
    title = "ЦБ сохранил ключевую ставку 14,0%"
    return NewsItem(
        title=title,
        published_on=date(2026, 9, 11),
        source_name="test",
        source_url="https://example.test/rate",
        factors=factors_in_text(title),
    )


class ScoringTest(unittest.TestCase):
    def test_rate_hits_transport_harder_than_restaurants(self) -> None:
        carrier = CompanyProfile(synthetic_u="c", industry="transport", has_leasing=True)
        restaurant = CompanyProfile(synthetic_u="r", industry="horeca")
        carrier_score, _ = score_item(carrier, _rate_item(), as_of=_AS_OF)
        restaurant_score, _ = score_item(restaurant, _rate_item(), as_of=_AS_OF)
        self.assertGreater(carrier_score, restaurant_score)
        self.assertIs(relevance_for(carrier_score), Relevance.IMPORTANT)

    def test_loan_flag_raises_rate_exposure(self) -> None:
        plain = CompanyProfile(synthetic_u="a", industry="services")
        borrower = CompanyProfile(synthetic_u="b", industry="services", has_loan=True)
        self.assertGreater(
            exposure(borrower)[Factor.RATE],
            exposure(plain)[Factor.RATE],
        )

    def test_steel_note_from_2021_is_hidden(self) -> None:
        company = CompanyProfile(synthetic_u="m", industry="metals")
        stale = NewsItem(
            title="Российская сталь: прогноз 1 квартала 2021",
            published_on=date(2021, 4, 15),
            source_name="Альфа-Банк",
            source_url="bank://K6",
            factors={Factor.COMMODITY: 3},
        )
        value, _ = score_item(company, stale, as_of=_AS_OF)
        self.assertEqual(value, 0.0)
        self.assertEqual(rank_for_company(company, [stale], as_of=_AS_OF), [])


class FeedTest(unittest.TestCase):
    def test_parse_rss_item(self) -> None:
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Ключевая ставка и кредиты</title>
            <link>https://example.test/1</link>
            <pubDate>Fri, 11 Sep 2026 12:00:00 +0300</pubDate>
            <description>Ставка осталась высокой.</description>
          </item>
        </channel></rss>
        """
        items = parse_rss(xml, "example")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_on, date(2026, 9, 11))
        self.assertIn(Factor.RATE, items[0].factors)

    def test_rate_news_uses_the_rate_card_not_the_later_bond_brief(self) -> None:
        card = latest_card_for(Factor.RATE)
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual(card.card_id, "K2")


if __name__ == "__main__":
    unittest.main()
