"""Citations for bank notes. The rate card stays K2; steel 2021 stays out."""

from __future__ import annotations

import unittest
from datetime import date

from decision_brief.bank_cards import (
    BANK_CARDS,
    cards_missing_page,
    cited_theses,
    current_citations,
    format_citation,
    latest_card_for,
    position_text,
)
from decision_brief.classify import factors_in_text
from decision_brief.models import CompanyProfile, Factor, NewsItem
from decision_brief.pipeline import explain, rank_for_company

_AS_OF = date(2026, 10, 21)
_RATE_TEXT = (
    "Ставка: 14,0%. Банк ожидает паузу 23 октября, "
    "14,0% на конец 2026 и 12,0% на конец 2027."
)


def _rate_item() -> NewsItem:
    title = "ЦБ сохранил ключевую ставку 14,0%"
    return NewsItem(
        title=title,
        published_on=date(2026, 9, 11),
        source_name="test",
        source_url="https://example.test/rate",
        factors=factors_in_text(title),
    )


def _card(card_id: str):
    return next(card for card in BANK_CARDS if card.card_id == card_id)


class BankCitationTest(unittest.TestCase):
    def test_rate_news_still_selects_k2(self) -> None:
        card = latest_card_for(Factor.RATE)
        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual(card.card_id, "K2")
        self.assertEqual(card.published_on, date(2026, 9, 11))
        text = position_text(card, _rate_item())
        self.assertIn(_RATE_TEXT, text)
        self.assertIn("ALFA-Macro_Insights-Policy_Rate_11Sep.pdf", text)
        self.assertIn("11.09.2026", text)
        self.assertIn("актуально", text)
        self.assertIn("Инфляция 2026: 7,5%.", text)
        self.assertIn("Курс на конец 2026: 87,2 руб./$.", text)
        self.assertNotIn("14,25", text)
        self.assertNotIn("14.25", text)

    def test_steel_2021_still_leaves_an_empty_feed(self) -> None:
        company = CompanyProfile(synthetic_u="m", industry="metals")
        stale = NewsItem(
            title="Российская сталь: прогноз 1 квартала 2021",
            published_on=date(2021, 4, 15),
            source_name="Альфа-Банк",
            source_url="bank://K6",
            factors={Factor.COMMODITY: 3},
        )
        self.assertEqual(rank_for_company(company, [stale], as_of=_AS_OF), [])
        steel = _card("K6")
        self.assertFalse(steel.fresh)
        self.assertTrue(cited_theses(steel))
        self.assertFalse(any(row.fresh for row in cited_theses(steel)))
        self.assertNotIn("K6", {row.card_id for row in current_citations()})

    def test_ready_sentences_keep_their_source_and_verified_pages(self) -> None:
        expected = {
            "K2": _RATE_TEXT,
            "K3": "Рынок труда жёсткий.",
            "K4": "Прогноз роста потребления в 4 квартале 2026 около нуля.",
            "K5": "ВВП 2026: +0,1%.",
            "K7": "67% кредитов юрлицам по плавающей ставке.",
        }
        for card_id, sentence in expected.items():
            card = _card(card_id)
            texts = [row.text for row in cited_theses(card)]
            self.assertIn(sentence, texts)
            self.assertTrue(card.page)
            self.assertTrue(card.source_url.startswith("https://drive.google.com/file/d/"))
            for row in cited_theses(card):
                self.assertEqual(row.page, card.page)
                self.assertEqual(row.filename, card.filename)
                self.assertEqual(row.published_on, card.published_on)
                line = format_citation(row)
                self.assertIn(f"стр. {card.page}", line)
                self.assertIn("пересказ:", line)

    def test_stale_rate_path_is_not_stored_on_any_thesis(self) -> None:
        blob = "\n".join(
            thesis.text for card in BANK_CARDS for thesis in card.theses
        )
        self.assertNotIn("14,25", blob)
        self.assertNotIn("14.25", blob)
        debt = [row for row in cited_theses(_card("K7")) if row.factor is Factor.DEBT]
        self.assertEqual(
            [row.text for row in debt],
            ["67% кредитов юрлицам по плавающей ставке."],
        )

    def test_only_unused_historical_card_has_no_verified_page(self) -> None:
        self.assertEqual(
            cards_missing_page(),
            ("K6",),
        )

    def test_explain_quotes_k2_and_keeps_the_news_source(self) -> None:
        company = CompanyProfile(
            synthetic_u="c",
            industry="transport",
            has_leasing=True,
        )
        ranked = rank_for_company(company, [_rate_item()], as_of=_AS_OF)
        self.assertTrue(ranked)
        text = explain(company, ranked[0])
        self.assertIn("Как оценивает банк.", text)
        self.assertIn("K2", text)
        self.assertIn(_RATE_TEXT, text)
        self.assertNotIn("14,25", text)
        self.assertIn("Вывод модели.", text)
        self.assertLess(text.index("Как оценивает банк."), text.index("Вывод модели."))
        self.assertIn("https://example.test/rate", text)


if __name__ == "__main__":
    unittest.main()
