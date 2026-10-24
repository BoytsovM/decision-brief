"""Model block: grounded numbers only, bank text stays put."""

from __future__ import annotations

import json
import os
import unittest
from datetime import date
from unittest.mock import patch

from decision_brief.models import (
    CompanyProfile,
    Factor,
    NewsItem,
    Relevance,
    ScoredItem,
)
from decision_brief.pipeline import explain, explain_for_role
from decision_brief.roles import Role, rank_for_role

_AS_OF = date(2026, 10, 21)
_ENV_KEYS = (
    "DECISION_BRIEF_MODEL",
    "DECISION_BRIEF_BASE_URL",
    "DECISION_BRIEF_API_KEY",
)


def _company() -> CompanyProfile:
    return CompanyProfile(
        synthetic_u="U_carrier",
        industry="transport",
        has_leasing=True,
    )


def _rate_item() -> NewsItem:
    return NewsItem(
        title="Уникальный заголовок который модель не видит",
        published_on=date(2026, 9, 11),
        source_name="test",
        source_url="https://example.test/rate",
        summary="Секретное описание 55,5",
        factors={Factor.RATE: 3},
    )


def _hidden_item() -> NewsItem:
    """Older than a year, so the feed drops it before any model call."""
    return NewsItem(
        title="СКРЫТЫЙ-ЗАГОЛОВОК",
        published_on=date(2021, 4, 15),
        source_name="test",
        source_url="https://example.test/hidden",
        summary="Скрытый текст 77,7",
        factors={Factor.RATE: 3},
    )


def _bank_section(card: str) -> str:
    lines = card.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("Как оценивает банк.")
    )
    end = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("Вывод модели")
    )
    return "\n".join(lines[start:end])


def _source_line(card: str) -> str:
    return next(
        line for line in card.splitlines() if line.startswith("Источник новости.")
    )


class _RecordingClient:
    """Stand-in for the gateway. Records the prompt and returns fixed JSON."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.payload


class ModelConclusionTest(unittest.TestCase):
    def test_without_key_explain_stays_empty(self) -> None:
        from decision_brief.conclusion import brief_card, client_from_env

        company = _company()
        ranked = rank_for_role(
            company,
            [_rate_item()],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        self.assertTrue(ranked)
        cleared = {key: "" for key in _ENV_KEYS}
        with patch.dict(os.environ, cleared, clear=False):
            self.assertIsNone(client_from_env())
            card = brief_card(
                company,
                ranked[0],
                shown=ranked,
                role=Role.TREASURER,
            )
        plain = explain_for_role(company, ranked[0], Role.TREASURER)
        self.assertEqual(card, plain)
        self.assertEqual(
            [line for line in card.splitlines() if line.startswith("Вывод модели")],
            ["Вывод модели."],
        )
        bare = explain(company, ranked[0])
        self.assertEqual(
            [line for line in bare.splitlines() if line.startswith("Вывод модели")],
            ["Вывод модели."],
        )

    def test_fake_client_drops_invented_number_and_keeps_bank_text(self) -> None:
        from decision_brief.conclusion import brief_card

        company = _company()
        shown_item = _rate_item()
        hidden = _hidden_item()
        ranked = rank_for_role(
            company,
            [shown_item, hidden],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        self.assertTrue(ranked)
        self.assertTrue(all(row.item.title != hidden.title for row in ranked))
        card = explain_for_role(company, ranked[0], Role.TREASURER)
        payload = json.dumps(
            {
                "последствия": "Ставка 14,0% уже в карточке.",
                "риск": (
                    "Ставка 14,0% уже в карточке. "
                    "Дополнительный удар 99,9 пункта."
                ),
                "возможность": "Пауза 23 октября уже названа в карточке банка.",
                "что проверить": "Сверить тезис карточки со ссылкой на новость.",
            },
            ensure_ascii=False,
        )
        client = _RecordingClient(payload)
        filled = brief_card(
            company,
            ranked[0],
            shown=ranked,
            role=Role.TREASURER,
            client=client,
        )
        self.assertEqual(len(client.prompts), 1)
        prompt = client.prompts[0]
        self.assertIn(company.synthetic_u, prompt)
        self.assertIn("казначей", prompt)
        self.assertIn("14,0%", prompt)
        self.assertIn(shown_item.source_url, prompt)
        self.assertNotIn(shown_item.title, prompt)
        self.assertNotIn("55,5", prompt)
        self.assertNotIn(hidden.title, prompt)
        self.assertNotIn("77,7", prompt)
        self.assertEqual(_bank_section(filled), _bank_section(card))
        self.assertEqual(_source_line(filled), _source_line(card))
        self.assertIn("Ставка 14,0% уже в карточке.", filled)
        self.assertIn("Пауза 23 октября уже названа в карточке банка.", filled)
        self.assertNotIn("Дополнительный удар 99,9 пункта.", filled)
        self.assertIn("99,9", filled)
        self.assertIn("Не хватило чисел во входных полях", filled)
        model_line = next(
            line for line in filled.splitlines() if line.startswith("Вывод модели")
        )
        bank_text = _bank_section(filled)
        self.assertNotIn(model_line, bank_text)

    def test_hidden_item_is_not_sent_to_the_client(self) -> None:
        from decision_brief.conclusion import brief_card

        company = _company()
        ranked = rank_for_role(
            company,
            [_rate_item()],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        hidden = ScoredItem(
            item=_hidden_item(),
            score=0.1,
            relevance=Relevance.HIDDEN,
            reasons=("скрыто",),
            bank_card=ranked[0].bank_card,
        )
        client = _RecordingClient("{}")
        filled = brief_card(
            company,
            hidden,
            shown=ranked,
            role=Role.TREASURER,
            client=client,
        )
        self.assertEqual(client.prompts, [])
        self.assertEqual(
            filled,
            explain_for_role(company, hidden, Role.TREASURER),
        )

    def test_unparsed_answer_does_not_leak_an_invented_number(self) -> None:
        from decision_brief.conclusion import brief_card

        company = _company()
        ranked = rank_for_role(
            company,
            [_rate_item()],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        card = explain_for_role(company, ranked[0], Role.TREASURER)
        client = _RecordingClient("Маржа вырастет на 99,9 и это не json")
        filled = brief_card(
            company,
            ranked[0],
            shown=ranked,
            role=Role.TREASURER,
            client=client,
        )
        self.assertEqual(_bank_section(filled), _bank_section(card))
        self.assertNotIn("99,9", filled)
        self.assertIn("не разобран", filled)

    def test_missing_url_and_vision_model_do_not_call_out(self) -> None:
        from decision_brief.conclusion import chat_completions_url, client_from_env

        missing_url = {
            "DECISION_BRIEF_MODEL": "text-model",
            "DECISION_BRIEF_BASE_URL": "",
            "DECISION_BRIEF_API_KEY": "test-key",
        }
        vision = {
            "DECISION_BRIEF_MODEL": "Qwen3-VL",
            "DECISION_BRIEF_BASE_URL": "https://gateway.internal/v1",
            "DECISION_BRIEF_API_KEY": "test-key",
        }
        with patch.dict(os.environ, missing_url, clear=False):
            self.assertIsNone(client_from_env())
        with patch.dict(os.environ, vision, clear=False):
            self.assertIsNone(client_from_env())
        self.assertEqual(
            chat_completions_url("https://gateway.internal/v1"),
            "https://gateway.internal/v1/chat/completions",
        )
        self.assertNotIn("api.openai.com", chat_completions_url("https://gateway.internal/v1"))

    def test_gateway_slug_is_accepted_and_translated(self) -> None:
        from decision_brief.conclusion import allowed_model, gateway_model_id

        self.assertTrue(allowed_model("z-ai/glm-5.3-flash"))
        self.assertTrue(allowed_model("GLM-5.3-Flash"))
        self.assertEqual(gateway_model_id("GLM-5.3-Flash"), "z-ai/glm-5.3-flash")
        self.assertEqual(gateway_model_id("z-ai/glm-5.3-flash"), "z-ai/glm-5.3-flash")
        self.assertFalse(allowed_model("qwen/qwen3-vl-30b-a3b-instruct"))

    def test_opened_card_calls_the_model_below_the_show_threshold(self) -> None:
        from decision_brief.conclusion import model_conclusion, opened_card_conclusion

        company = _company()
        hidden = ScoredItem(
            item=_hidden_item(),
            score=0.1,
            relevance=Relevance.HIDDEN,
            reasons=("Ниже порога показа.",),
            bank_card=None,
        )
        payload = json.dumps(
            {
                "последствия": "Нагрузка на лизинг не снижается.",
                "риск": "Пауза оставляет деньги дорогими.",
                "возможность": "Есть время пересмотреть график.",
                "что проверить": "Долю лизинга в платежах.",
            },
            ensure_ascii=False,
        )
        client = _RecordingClient(payload)
        text = opened_card_conclusion(
            company,
            hidden,
            role=Role.TREASURER,
            client=client,
        )
        self.assertEqual(len(client.prompts), 1)
        self.assertIn("Нагрузка на лизинг не снижается.", text)
        self.assertNotIn("77,7", client.prompts[0])
        skipped = model_conclusion(
            company,
            hidden,
            role=Role.TREASURER,
            client=client,
            shown=(hidden,),
        )
        self.assertEqual(skipped, "")
        self.assertEqual(len(client.prompts), 1)

    def test_reader_parts_drop_internal_tokens(self) -> None:
        from decision_brief.conclusion import reader_model_parts

        raw = json.dumps(
            {
                "последствия": (
                    "Почему кредиты остаются дорогими. "
                    "Платежи по лизингу не снизятся в ближайшие месяцы. "
                    "Пауза 23 октября оставляет стоимость денег высокой. "
                    "На ваш бизнес это влияет через стоимость кредита и лизинга."
                ),
                "риск": "Для U_1595 retail при ставке 14,0% лизинг дороже.",
                "возможность": "Пауза даёт время пересмотреть график лизинга.",
                "дальше": "Решение 23 октября задаст платежи до конца года.",
                "что проверить": "Долю долга по плавающей ставке.",
                "ответ": "Доля плавающей ставки в данных не указана.",
            },
            ensure_ascii=False,
        )
        source = "Ставка 14,0%. Пауза 23 октября."
        parts = reader_model_parts(raw, source)
        self.assertNotIn("U_1595", parts["risk"])
        self.assertNotIn("retail", parts["risk"].casefold())
        self.assertIn("14,0%", parts["risk"])
        self.assertIn("лизинг", parts["opportunity"])
        self.assertTrue(parts["gaps"].startswith("Долю долга"))
        self.assertNotIn("очему", parts["summary"].casefold())
        self.assertEqual(parts["summary"].count("."), 4)
        self.assertIn("На ваш бизнес это влияет через", parts["summary"])
        self.assertIn("23 октября", parts["next"])
        self.assertIn("не указана", parts["answer"])
        task = json.dumps({"дальше": "Проверить валютную позицию и график."}, ensure_ascii=False)
        self.assertEqual(reader_model_parts(task, source)["next"], "")


if __name__ == "__main__":
    unittest.main()
