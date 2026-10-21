"""One brief pass on fixtures: log the steps, do not open a PDF or the network."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from decision_brief.feeds import parse_rss
from decision_brief.models import Factor, NewsItem
from decision_brief.roles import Role

_AS_OF = date(2026, 10, 21)
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_COMPANIES = _FIXTURES / "brief_companies.csv"
_PAYMENTS = _FIXTURES / "payments_small.csv"
_RSS = _FIXTURES / "rss"
_HIDDEN = "СКРЫТЫЙ-МАТЕРИАЛ"
_STEPS = (
    "1. Профиль компании и группы",
    "2. Роль",
    "3. Ранжирование новостей",
    "4. Свежая карточка по главному фактору",
    "5. Контрагенты с долей от 10%",
    "6. Вызов модели",
    "7. Проверка",
)
_NO_CARD = "Свежей карточки банка по этому фактору нет."


class _RecordingClient:
    """Stand-in gateway. Records each prompt and returns one fixed answer."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.payload


def _items() -> list[NewsItem]:
    """Three fixture articles plus one stale item the model must not see."""
    specs = (
        ("gazeta_rate_credit.xml", "Газета.Ru"),
        ("interfax_deposit_tax.xml", "Интерфакс"),
        ("cbr_rate_dynamics.xml", "Банк России"),
    )
    items: list[NewsItem] = []
    for name, source in specs:
        xml_text = (_RSS / name).read_text(encoding="utf-8")
        items.extend(parse_rss(xml_text, source))
    items.append(
        NewsItem(
            title=_HIDDEN,
            published_on=date(2021, 4, 15),
            source_name="архив",
            source_url="https://example.test/hidden-material",
            summary="секрет 77,7",
            factors={Factor.COMMODITY: 3},
        )
    )
    return items


def _payload() -> str:
    return json.dumps(
        {
            "последствия": "Ставка 14,0% уже во входных полях.",
            "риск": "Выдуманный запас 99,9 пункта.",
            "возможность": "Пауза до 23 октября следует из карточки.",
            "что проверить": "Сверить лизинг со ссылкой на новость.",
        },
        ensure_ascii=False,
    )


def _log_text(log: tuple[str, ...]) -> str:
    return "\n".join(log)


class BriefPassTest(unittest.TestCase):
    def test_fixture_pass_logs_sources_features_and_discarded_phrases(self) -> None:
        from decision_brief.brief_pass import prepare_brief

        client = _RecordingClient(_payload())
        result = prepare_brief(
            "U_focal",
            _items(),
            Role.TREASURER,
            companies_path=_COMPANIES,
            payments_path=_PAYMENTS,
            as_of=_AS_OF,
            client=client,
        )
        log = _log_text(result.log)
        positions = [log.find(step) for step in _STEPS]
        self.assertTrue(all(position >= 0 for position in positions))
        self.assertEqual(positions, sorted(positions))

        self.assertIn("Признаки компании:", log)
        self.assertIn("лизинг", log)
        self.assertIn("49.41", log)
        self.assertIn("32300000000", log)
        self.assertIn("крупный штат", log)
        self.assertIn("G_transport", log)
        self.assertIn("казначей", log)

        self.assertIn("https://www.gazeta.ru/business/news/2026/10/20/29561401.shtml", log)
        self.assertIn("https://www.interfax.ru/business/1119596", log)
        self.assertIn("https://www.cbr.ru/press/event/?id=32903", log)
        self.assertIn("Газета.Ru", log)
        self.assertIn("Интерфакс", log)
        self.assertIn("Банк России", log)
        self.assertIn("K2", log)

        self.assertIn("U_big", log)
        self.assertIn("U_exact", log)
        self.assertNotIn("U_small", log)
        self.assertIn("Выдуманный запас 99,9 пункта.", log)
        self.assertIn("Отброшенные фразы:", log)
        self.assertIn("Выдуманный запас 99,9 пункта.", result.discarded_phrases)
        self.assertIn("Проверка чисел: каждое число вывода есть во входе.", log)
        self.assertIn("позиция банка отделена от вывода модели", log)
        self.assertIn("у вывода есть ссылка", log)

        self.assertEqual(len(client.prompts), 1)
        prompt = client.prompts[0]
        self.assertNotIn(_HIDDEN, prompt)
        self.assertNotIn("77,7", prompt)
        self.assertNotIn(_HIDDEN, log)
        self.assertNotIn(_HIDDEN, result.answer)
        self.assertNotIn("77,7", result.answer)
        self.assertNotIn("Выдуманный запас 99,9 пункта.", result.answer)
        self.assertNotIn("99,9", result.answer)
        self.assertIn("14,0%", result.answer)
        self.assertIn("Источник вывода.", result.answer)
        self.assertIn("Как оценивает банк.", result.answer)
        self.assertEqual(
            sum(line.startswith("Вывод модели") for line in result.answer.splitlines()),
            1,
        )
        self.assertIn("U_big", result.answer)
        self.assertNotIn("U_small", result.answer)

    def test_missing_card_is_stated_and_pdf_is_not_opened(self) -> None:
        from decision_brief import brief_pass
        from decision_brief.brief_pass import prepare_brief

        source = Path(brief_pass.__file__).read_text(encoding="utf-8")
        self.assertNotIn("read_pdf", source)
        client = _RecordingClient(
            json.dumps(
                {
                    "последствия": "Числовых последствий модель не добавляет.",
                    "риск": "",
                    "возможность": "",
                    "что проверить": "",
                },
                ensure_ascii=False,
            )
        )
        item = NewsItem(
            title="Ключевая ставка без карточки",
            published_on=date(2026, 9, 11),
            source_name="Газета.Ru",
            source_url="https://example.test/no-card",
            factors={Factor.RATE: 3},
        )
        with patch("decision_brief.roles.latest_card_for", return_value=None):
            result = prepare_brief(
                "U_focal",
                [item],
                Role.TREASURER,
                companies_path=_COMPANIES,
                payments_path=_PAYMENTS,
                as_of=_AS_OF,
                client=client,
            )
        text = _log_text(result.log)
        self.assertIn(_NO_CARD, text)
        self.assertIn(_NO_CARD, result.answer)
        self.assertNotIn("ALFA-Macro_Insights", result.answer)
        self.assertEqual(len(client.prompts), 1)
        self.assertIn(_NO_CARD, client.prompts[0])
        self.assertIn("https://example.test/no-card", result.answer)

    def test_follow_up_reuses_the_profile_and_skips_hidden_news(self) -> None:
        from decision_brief.brief_pass import prepare_brief, prepare_follow_up

        client = _RecordingClient(_payload())
        items = _items()
        first = prepare_brief(
            "U_focal",
            items,
            Role.TREASURER,
            companies_path=_COMPANIES,
            payments_path=_PAYMENTS,
            as_of=_AS_OF,
            client=client,
        )
        question = "Что проверить казначею по лизингу?"
        second = prepare_follow_up(
            "U_focal",
            items,
            Role.TREASURER,
            question,
            companies_path=_COMPANIES,
            payments_path=_PAYMENTS,
            as_of=_AS_OF,
            client=client,
        )
        self.assertEqual(len(client.prompts), 2)
        self.assertNotIn(question, client.prompts[0])
        self.assertIn(question, client.prompts[1])
        for prompt in client.prompts:
            self.assertNotIn(_HIDDEN, prompt)
            self.assertNotIn("77,7", prompt)
        self.assertIn("Профиль тот же: U_focal.", _log_text(second.log))
        self.assertNotIn("Профиль тот же:", _log_text(first.log))
        first_features = next(
            line for line in first.log if line.startswith("Признаки компании:")
        )
        second_features = next(
            line for line in second.log if line.startswith("Признаки компании:")
        )
        self.assertEqual(first_features, second_features)
        self.assertIn(question, second.answer)


if __name__ == "__main__":
    unittest.main()
