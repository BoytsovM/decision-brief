"""Feed JSON is projected from parsed items, not from the Figma copy."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from decision_brief.demo import DEMO_DATE, demo_news
from decision_brief.feeds import parse_rss
from decision_brief.models import NewsItem
from decision_brief.roles import Role
from decision_brief.screen import NewsLoad, load_demo_companies, sample_companies_path
from decision_brief.web_api import build_feed, plain_text
from decision_brief.web_server import combine_live, user_events

_RSS = Path(__file__).resolve().parent / "fixtures" / "rss"
_AS_OF = date(2026, 10, 21)


class FeedPayloadTest(unittest.TestCase):
    def test_ranked_row_comes_from_the_rss_item(self) -> None:
        xml_text = (_RSS / "cbr_rate_dynamics.xml").read_text(encoding="utf-8")
        items = parse_rss(xml_text, "Банк России")
        companies = load_demo_companies(sample_companies_path())
        company = next(row for row in companies if row.synthetic_u == "U_sample_transport")
        payload = build_feed(
            company,
            items,
            Role.TREASURER,
            as_of=_AS_OF,
            source="live",
            notice="",
            loaded_at="21.10.2026, 12:00",
        )
        self.assertEqual(payload["incoming"], 1)
        self.assertEqual(payload["source"], "live")
        shown = payload["items"]
        self.assertIsInstance(shown, list)
        assert isinstance(shown, list)
        self.assertGreaterEqual(len(shown), 1)
        row = shown[0]
        self.assertEqual(row["title"], items[0].title)
        self.assertNotEqual(row["headline"], row["title"])
        self.assertIn("?", str(row["headline"]))
        self.assertIn("ставк", str(row["summary"]).casefold())
        self.assertNotIn("Топливо дорожает", str(row["title"]))
        self.assertNotIn("Топливо дорожает", str(row["headline"]))
        self.assertIn(",", str(row["score"]))
        card = row["card"]
        assert isinstance(card, dict)
        self.assertEqual(card["model"], "")
        self.assertNotIn("экспозиция", str(card["why"]))
        self.assertNotIn(".pdf", str(card["bank"]).casefold())
        self.assertNotIn("CL_PRODUCT", str(card.get("signs", "")))
        self.assertIn("14,0%", str(card["bank"]))
        effects = card["effects"]
        assert isinstance(effects, dict)
        risk_text = " ".join(str(row["text"]) for row in effects["risks"])
        next_text = " ".join(str(row["text"]) for row in effects["next"])
        self.assertIn("лизинг", risk_text.casefold())
        self.assertIn("паузу", str(card["bank"]).casefold())
        self.assertIn("Материал банка", str(card["bank"]))
        self.assertNotIn("паузу", next_text.casefold())
        self.assertIn("прогноз банка", next_text.casefold())
        self.assertNotIn("ОКВЭД", str(card["why"]))
        self.assertNotIn("парк на бензине", risk_text.casefold())
        self.assertIn("Банк России", str(row["source_name"]))

    def test_plain_text_strips_markup(self) -> None:
        self.assertEqual(plain_text("<b>Ставка</b>  <!--x-->  14"), "Ставка 14")

    def test_parsed_story_stays_visible_when_it_misses_the_horeca_threshold(self) -> None:
        items = demo_news()
        companies = load_demo_companies(sample_companies_path())
        carrier = next(row for row in companies if row.synthetic_u == "U_sample_transport")
        cafe = next(row for row in companies if row.synthetic_u == "U_sample_horeca")
        carrier_feed = build_feed(
            carrier, items, Role.TREASURER, as_of=DEMO_DATE,
            source="demo", notice="", loaded_at="21.10.2026",
        )
        cafe_feed = build_feed(
            cafe, items, Role.TREASURER, as_of=DEMO_DATE,
            source="demo", notice="", loaded_at="21.10.2026",
        )
        owner_feed = build_feed(
            cafe, items, Role.OWNER, as_of=DEMO_DATE,
            source="demo", notice="", loaded_at="21.10.2026",
        )
        rate = "Демо: ключевая ставка сохранена"
        demand = "Демо: спрос в общепите замедляется"
        self.assertIn(rate, _titles(carrier_feed))
        self.assertIn(rate, _titles(cafe_feed))
        cafe_rows = cafe_feed["items"]
        assert isinstance(cafe_rows, list)
        rate_row = next(row for row in cafe_rows if row["title"] == rate)
        self.assertEqual(rate_row["level"], "low")
        self.assertEqual(len(cafe_rows), cafe_feed["incoming"])
        self.assertIn(demand, _titles(owner_feed))

    def test_failed_rss_keeps_the_previous_live_feed(self) -> None:
        previous = demo_news()[:1]
        kept, notice = combine_live(previous, NewsLoad((), True))
        self.assertEqual(kept[0].title, previous[0].title)
        self.assertIn("уже посчитанная", notice)
        empty, fresh = combine_live(previous, NewsLoad((), False))
        self.assertEqual(empty, [])
        self.assertEqual(fresh, "")

    def test_user_event_uses_the_same_parser_rules(self) -> None:
        created = user_events({
            "title": "Спрос в ресторанах меняется",
            "body": "Вымышленный опрос показывает рост потребления и спроса в общепите",
            "published": "2026-10-21",
        }, as_of=DEMO_DATE)
        self.assertEqual(len(created), 1)
        self.assertIsInstance(created[0], NewsItem)
        self.assertTrue(created[0].source_url.startswith("https://"))


def _titles(payload: dict[str, object]) -> list[str]:
    rows = payload["items"]
    assert isinstance(rows, list)
    return [str(row["title"]) for row in rows]


if __name__ == "__main__":
    unittest.main()
