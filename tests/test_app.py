"""Streamlit UI acceptance: real script, forms and reruns, no external services."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements.txt to run the UI acceptance test")
class AppAcceptanceTest(unittest.TestCase):
    def test_jury_can_navigate_change_profile_add_news_and_ask(self):
        env = {key: "" for key in ("DECISION_BRIEF_MODEL", "DECISION_BRIEF_BASE_URL",
              "DECISION_BRIEF_API_KEY", "DECISION_BRIEF_COMPANIES", "DECISION_BRIEF_PAYMENTS",
              "DECISION_BRIEF_NEWS_MODE")}
        with patch.dict(os.environ, env), patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "src/decision_brief/app.py"), default_timeout=20).run()
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label == "Открыть бизнес-аналитику").click().run()
            self.assertFalse(app.exception)
            transport = app.selectbox(key="company").value
            self.assertIn("transport", transport)
            company_options = app.selectbox(key="company").options
            app.selectbox(key="company").select(company_options[1]).run()
            self.assertIn("horeca", app.selectbox(key="company").value)
            app.selectbox(key="role").select("собственник").run()
            next(x for x in app.text_input if x.label == "Заголовок").set_value("Новая новость: спрос в ресторанах растёт")
            next(x for x in app.text_area if x.label == "Текст события").set_value("Тестовый опрос: потребление и спрос меняются.")
            next(b for b in app.button if b.label == "Добавить материал").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Новая новость" in x.value for x in app.subheader))
            next(x for x in app.text_input if x.label == "Уточняющий вопрос").set_value("Что означает новый спрос?")
            next(b for b in app.button if b.label == "Подготовить анализ").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Интерпретация по правилам" in x.value for x in app.caption))


if __name__ == "__main__":
    unittest.main()
