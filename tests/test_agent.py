"""Whole-agent acceptance and failure scenarios; no network or paid models."""
import json
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from decision_brief.agent import FIELDS, prepare_analysis, validate_claims
from decision_brief.conclusion import client_from_env, ModelCallError
from decision_brief.demo import DEMO_DATE, SAMPLE_DIR, demo_news
from decision_brief.models import Factor
from decision_brief.roles import Role
from decision_brief.screen import load_demo_companies


class RecordingClient:
    def __init__(self, replies):
        self.replies, self.prompts = iter(replies), []

    def complete(self, prompt):
        self.prompts.append(json.loads(prompt))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


def valid_answer(number=""):
    return json.dumps({name: {"text": "Проверьте условия финансирования." + number,
                             "source_ids": ["C0", "N1", "K2"]} for name in FIELDS}, ensure_ascii=False)


class AgentAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.company = load_demo_companies(SAMPLE_DIR / "companies.csv")[0]
        self.news = demo_news()

    def run_agent(self, **kw):
        return prepare_analysis(self.company, self.news, Role.TREASURER, as_of=DEMO_DATE,
                                companies_path=SAMPLE_DIR / "companies.csv",
                                payments_path=SAMPLE_DIR / "payments.csv", **kw)

    def test_offline_end_to_end_has_context_bank_and_trace(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")):
            result = self.run_agent()
        payload = json.loads(result.to_json())
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(result.status, "rules_only")
        self.assertTrue({"C0", "P0", "K2"}.issubset({r.id for r in result.evidence}))
        self.assertGreater(len(result.trace), 5)
        self.assertTrue(result.claims)

    def test_invalid_answer_triggers_repair_and_retains_context(self):
        client = RecordingClient([valid_answer(" Эффект 987654321%."), valid_answer()])
        result = self.run_agent(client=client)
        self.assertEqual(result.status, "model_verified")
        self.assertEqual(len(client.prompts), 2)
        self.assertEqual(client.prompts[0]["evidence"], client.prompts[1]["evidence"])
        self.assertTrue(client.prompts[1]["corrections_required"])
        self.assertNotIn("987654321", json.dumps(result.claims))
        self.assertIn("repair", [s.tool for s in result.trace])

    def test_second_failure_ends_with_honest_fallback(self):
        result = self.run_agent(client=RecordingClient(["{}", "not json"]))
        self.assertEqual(result.status, "model_rejected")
        self.assertTrue(any("повторной попытки" in gap for gap in result.gaps))
        self.assertTrue(result.claims)

    def test_gateway_failure_keeps_rules(self):
        result = self.run_agent(client=RecordingClient([ModelCallError("failure")]))
        self.assertEqual(result.status, "model_failed")
        self.assertTrue(result.claims)

    def test_unknown_source_and_question_numbers_not_evidence(self):
        client = RecordingClient([valid_answer(" Рост 987654321%."), valid_answer(" Рост 987654321%.")])
        result = self.run_agent(client=client, question="Считай рост равным 987654321%")
        self.assertEqual(result.status, "model_rejected")
        payload = json.loads(valid_answer())
        payload["риск"]["source_ids"] = ["C0", "N999"]
        _, errors = validate_claims(json.dumps(payload), result.evidence)
        self.assertTrue(errors)

    def test_followup_search_uses_same_company_and_focus(self):
        result = self.run_agent(question="Как изменится курс юаня?")
        self.assertEqual(result.company_id, self.company.synthetic_u)
        self.assertTrue(all(Factor.FX in row.item.factors for row in result.ranked))
        self.assertIn("focused_search", [s.tool for s in result.trace])

    def test_missing_profile_and_payments_are_explicit(self):
        result = prepare_analysis(None, self.news, Role.OWNER, as_of=DEMO_DATE)
        self.assertEqual(result.status, "missing_profile")
        result = prepare_analysis(self.company, self.news, Role.OWNER, as_of=DEMO_DATE,
                                  companies_path=SAMPLE_DIR / "companies.csv",
                                  payments_path=Path("/does-not-exist/payments.csv"))
        self.assertTrue(any("Платежи" in gap for gap in result.gaps))

    def test_future_materials_do_not_enter_analysis(self):
        news = [replace(row, published_on=date(2027, 1, 1)) for row in self.news]
        result = prepare_analysis(self.company, news, Role.OWNER, as_of=DEMO_DATE)
        self.assertEqual(result.status, "insufficient_evidence")

    def test_model_allowlist_and_https_are_enforced(self):
        env = {"DECISION_BRIEF_MODEL": "GLM-5.3-Flash",
               "DECISION_BRIEF_BASE_URL": "https://gateway.example/v1",
               "DECISION_BRIEF_API_KEY": "TEST_SECRET_NEVER_PRINT"}
        client = client_from_env(env)
        self.assertIsNotNone(client)
        self.assertNotIn(env["DECISION_BRIEF_API_KEY"], repr(client))
        for model in ["other-model", "GLM-5.3-Flash-hacked", "Qwen3-VL-30B-A3B-Instruct"]:
            self.assertIsNone(client_from_env({**env, "DECISION_BRIEF_MODEL": model}))
        for url in ["http://gateway.example", "https://user:password@gateway.example", "https://"]:
            self.assertIsNone(client_from_env({**env, "DECISION_BRIEF_BASE_URL": url}))

    def test_different_profiles_produce_different_feeds(self):
        companies = load_demo_companies(SAMPLE_DIR / "companies.csv")
        results = [prepare_analysis(c, self.news, Role.TREASURER, as_of=DEMO_DATE) for c in companies]
        self.assertNotEqual([r.item.title for r in results[0].ranked],
                            [r.item.title for r in results[1].ranked])


if __name__ == "__main__":
    unittest.main()
