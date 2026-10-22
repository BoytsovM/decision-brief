"""Unverified chart transcription. The feed tests do not call a vision model."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decision_brief.bank_cards import BANK_CARDS, cards_missing_page
from decision_brief.chart_draft import (
    UNVERIFIED,
    default_draft_path,
    empty_draft,
    gap_page_targets,
    load_draft,
    parse_transcription,
    pdf_name_matches,
    readings_for_user_response,
    save_draft,
    transcription_prompt,
)

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _ROOT / "src" / "decision_brief"
_WORKING_PATH = (
    "app.py",
    "screen.py",
    "feeds.py",
    "conclusion.py",
    "brief_pass.py",
    "pipeline.py",
    "bank_cards.py",
    "__main__.py",
)
_SAMPLE = """
[
  {
    "страница": "2",
    "название графика": "Ключевая ставка",
    "ряд": "факт",
    "число": "14,0",
    "единица": "%",
    "дата": "11.09.2026",
    "status": "проверено"
  }
]
"""


class TranscriptionPromptTest(unittest.TestCase):
    def test_prompt_asks_for_chart_fields_and_not_for_an_opinion(self) -> None:
        text = transcription_prompt(3)
        for field in (
            "страница",
            "название графика",
            "ряд",
            "число",
            "единица",
            "дата",
        ):
            self.assertIn(field, text)
        self.assertIn("3", text)
        folded = text.casefold()
        self.assertNotIn("как оценивает", folded)
        self.assertNotIn("каково мнение", folded)
        self.assertNotIn("?", text)


class ParseTranscriptionTest(unittest.TestCase):
    def test_rows_stay_unverified_strings(self) -> None:
        rows = parse_transcription(
            _SAMPLE,
            card_id="K2",
            filename="opened.pdf",
            card_filename="card.pdf",
            pdf_page=2,
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.status, UNVERIFIED)
        self.assertEqual(row.status, "не проверено")
        self.assertEqual(row.card_id, "K2")
        self.assertEqual(row.filename, "opened.pdf")
        self.assertEqual(row.card_filename, "card.pdf")
        self.assertEqual(row.pdf_page, "2")
        self.assertEqual(row.page, "2")
        self.assertEqual(row.chart_title, "Ключевая ставка")
        self.assertEqual(row.series, "факт")
        self.assertEqual(row.number, "14,0")
        self.assertEqual(row.unit, "%")
        self.assertEqual(row.observed_on, "11.09.2026")

    def test_unparsed_text_and_an_empty_number_add_no_row(self) -> None:
        self.assertEqual(
            parse_transcription(
                "это не json",
                card_id="K1",
                filename="a.pdf",
                card_filename="a.pdf",
                pdf_page=1,
            ),
            (),
        )
        raw = '[{"страница":"1","название графика":"Пусто","ряд":"","число":"","единица":"","дата":""}]'
        self.assertEqual(
            parse_transcription(
                raw,
                card_id="K1",
                filename="a.pdf",
                card_filename="a.pdf",
                pdf_page=1,
            ),
            (),
        )


class DraftSeparationTest(unittest.TestCase):
    def test_user_response_receives_no_draft_numbers(self) -> None:
        rows = parse_transcription(
            _SAMPLE,
            card_id="K2",
            filename="opened.pdf",
            card_filename="card.pdf",
            pdf_page=2,
        )
        draft = empty_draft(model="Qwen3-VL-30B-A3B-Instruct", note="")
        stored = type(draft)(
            status="проверено",
            model=draft.model,
            note=draft.note,
            missing=(),
            rows=rows,
        )
        self.assertEqual(readings_for_user_response(stored), ())

    def test_saved_draft_does_not_fill_bank_card_pages(self) -> None:
        rows = parse_transcription(
            _SAMPLE,
            card_id="K2",
            filename="opened.pdf",
            card_filename="card.pdf",
            pdf_page=2,
        )
        draft = empty_draft(model="Qwen3-VL-30B-A3B-Instruct", note="черновик")
        draft = type(draft)(
            status=draft.status,
            model=draft.model,
            note=draft.note,
            missing=("K9",),
            rows=rows,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chart_transcription_draft.json"
            save_draft(path, draft)
            loaded = load_draft(path)
        self.assertEqual(loaded.status, UNVERIFIED)
        self.assertEqual(loaded.rows[0].status, UNVERIFIED)
        self.assertEqual(loaded.missing, ("K9",))
        self.assertEqual(readings_for_user_response(loaded), ())
        self.assertEqual(cards_missing_page(), ("K6",))
        self.assertEqual(
            cards_missing_page(),
            ("K6",),
        )

    def test_gap_list_matches_cards_and_leaves_them_empty(self) -> None:
        targets = gap_page_targets()
        self.assertEqual(
            tuple(item.card_id for item in targets),
            ("K6",),
        )
        filenames = {item.card_id: item.filename for item in targets}
        self.assertEqual(filenames["K6"], "ALFA_Russian_Steels_1K21.pdf")
        self.assertTrue(
            pdf_name_matches(
                filenames["K6"],
                "ALFA_Russian_Steels_1К21PreviewUpdate_15Apr2021.pdf",
            )
        )
        self.assertFalse(pdf_name_matches("ALFA-7M26.pdf", "ALFA-consumption.pdf"))
        self.assertEqual(cards_missing_page(), ("K6",))

    def test_stored_draft_stays_beside_the_cards_and_out_of_the_answer(self) -> None:
        path = default_draft_path()
        self.assertEqual(path.parent.name, "decision_brief")
        self.assertNotEqual(path.name, "bank_cards.py")
        loaded = load_draft(path)
        self.assertEqual(loaded.status, UNVERIFIED)
        self.assertTrue(all(row.status == UNVERIFIED for row in loaded.rows))
        self.assertEqual(readings_for_user_response(loaded), ())
        self.assertEqual(cards_missing_page(), ("K6",))


class FeedIndependenceTest(unittest.TestCase):
    def test_feed_and_the_working_path_do_not_import_the_draft(self) -> None:
        feed_test = (_ROOT / "tests" / "test_feeds.py").read_text(encoding="utf-8")
        feeds = (_PACKAGE / "feeds.py").read_text(encoding="utf-8")
        for text in (feed_test, feeds):
            self.assertNotIn("chart_draft", text)
            self.assertNotIn("Qwen3-VL", text)
            self.assertNotIn("transcribe_gap", text)
        for name in _WORKING_PATH:
            source = (_PACKAGE / name).read_text(encoding="utf-8")
            self.assertNotIn("chart_draft", source)
            self.assertNotIn("transcribe_gap", source)
        module = (_PACKAGE / "chart_draft.py").read_text(encoding="utf-8")
        self.assertNotIn("urlopen", module)
        self.assertNotIn("Qwen3-VL", module)
