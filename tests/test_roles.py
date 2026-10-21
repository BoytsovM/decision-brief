"""Role feed: order changes with the person, the model block stays empty."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from decision_brief.bank_cards import BANK_CARDS
from decision_brief.counterparties import CounterpartyShare
from decision_brief.models import CompanyProfile, Factor, NewsItem, Relevance, ScoredItem
from decision_brief.pipeline import explain, explain_for_role
from decision_brief.roles import (
    Role,
    assumed_role_weights,
    company_consequence,
    counterparty_reasons,
    find_role_workbook,
    load_role_weights,
    rank_for_role,
    score_for_role,
    weight_source,
    workbook_sheet_names,
)
from decision_brief.scoring import relevance_for, score_item

_AS_OF = date(2026, 10, 21)
_PUBLISHED = date(2026, 9, 11)


def _item(title: str, factors: dict[Factor, int], summary: str = "") -> NewsItem:
    return NewsItem(
        title=title,
        published_on=_PUBLISHED,
        source_name="test",
        source_url=f"https://example.test/{title}",
        summary=summary,
        factors=factors,
    )


def _write_xlsx(path: Path, sheet_name: str, rows: list[list[object]]) -> None:
    """Minimal workbook. Text cells are shared strings, numbers are numeric."""
    strings: list[str] = []
    index: dict[str, int] = {}

    def share(text: str) -> int:
        if text not in index:
            index[text] = len(strings)
            strings.append(text)
        return index[text]

    sheet_rows: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column, value in enumerate(row):
            ref = f"{_column(column)}{row_number}"
            if isinstance(value, str):
                cells.append(f'<c r="{ref}" t="s"><v>{share(value)}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    shared = "".join(f"<si><t>{_xml(text)}</t></si>" for text in strings)
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{_xml(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(strings)}" uniqueCount="{len(strings)}">{shared}</sst>'
    )
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("[Content_Types].xml", content_types)
        book.writestr("_rels/.rels", root_rels)
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", rels)
        book.writestr("xl/worksheets/sheet1.xml", sheet)
        book.writestr("xl/sharedStrings.xml", shared_xml)


def _column(index: int) -> str:
    letters = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class RoleFeedTest(unittest.TestCase):
    def test_carrier_and_restaurant_scores_differ_on_one_rate_item(self) -> None:
        carrier = CompanyProfile(
            synthetic_u="c",
            industry="transport",
            has_leasing=True,
        )
        restaurant = CompanyProfile(synthetic_u="r", industry="horeca")
        item = _item("Ставка", {Factor.RATE: 3})
        carrier_company, _ = score_item(carrier, item, as_of=_AS_OF)
        restaurant_company, _ = score_item(restaurant, item, as_of=_AS_OF)
        self.assertGreater(carrier_company, restaurant_company)
        carrier_role, _ = score_for_role(
            carrier,
            item,
            Role.TREASURER,
            as_of=_AS_OF,
        )
        restaurant_role, _ = score_for_role(
            restaurant,
            item,
            Role.TREASURER,
            as_of=_AS_OF,
        )
        self.assertGreater(carrier_role, restaurant_role)
        self.assertIs(relevance_for(carrier_role), Relevance.IMPORTANT)

    def test_treasurer_and_owner_order_the_same_news_differently(self) -> None:
        company = CompanyProfile(synthetic_u="h", industry="housing")
        items = [
            _item("Ставка", {Factor.RATE: 3}),
            _item("Спрос", {Factor.DEMAND: 3}),
        ]
        treasurer = rank_for_role(company, items, Role.TREASURER, as_of=_AS_OF)
        owner = rank_for_role(company, items, Role.OWNER, as_of=_AS_OF)
        treasurer_titles = [row.item.title for row in treasurer]
        owner_titles = [row.item.title for row in owner]
        self.assertNotEqual(treasurer_titles, owner_titles)
        if weight_source().assumed:
            self.assertEqual(treasurer_titles, ["Ставка", "Спрос"])
            self.assertEqual(owner_titles, ["Спрос", "Ставка"])

    def test_stale_item_stays_hidden_for_a_role(self) -> None:
        company = CompanyProfile(synthetic_u="m", industry="metals")
        stale = NewsItem(
            title="Сталь 2021",
            published_on=date(2021, 4, 15),
            source_name="test",
            source_url="bank://K6",
            factors={Factor.COMMODITY: 3},
        )
        self.assertEqual(
            rank_for_role(company, [stale], Role.OWNER, as_of=_AS_OF),
            [],
        )

    def test_consequence_follows_the_profile(self) -> None:
        item = _item("Ставка", {Factor.RATE: 3})
        carrier = CompanyProfile(
            synthetic_u="c",
            industry="transport",
            has_leasing=True,
        )
        restaurant = CompanyProfile(synthetic_u="r", industry="horeca")
        carrier_text = company_consequence(carrier, item)
        restaurant_text = company_consequence(restaurant, item)
        self.assertNotEqual(carrier_text, restaurant_text)
        self.assertIn("бьёт по лизингу", carrier_text)
        self.assertIn("грузоперевоз", carrier_text.casefold())
        self.assertIn("общепит", restaurant_text.casefold())
        self.assertNotIn("бьёт по лизингу", restaurant_text)

    def test_model_block_stays_empty_and_the_bank_card_is_fresh(self) -> None:
        company = CompanyProfile(
            synthetic_u="c",
            industry="transport",
            has_leasing=True,
        )
        ranked = rank_for_role(
            company,
            [_item("Ставка", {Factor.RATE: 3})],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        self.assertTrue(ranked)
        text = explain_for_role(company, ranked[0], Role.TREASURER)
        self.assertIn("роль казначей", text)
        self.assertIn("лизинг", text.casefold())
        self.assertEqual(
            [line for line in text.splitlines() if line.startswith("Вывод модели")],
            ["Вывод модели."],
        )
        self.assertNotIn("LLM", text)
        self.assertIn("K2", text)
        self.assertIn("https://example.test/Ставка", text)
        stale = next(card for card in BANK_CARDS if card.card_id == "K6")
        hidden = ScoredItem(
            item=_item("Сталь", {Factor.COMMODITY: 3}),
            score=0.5,
            relevance=Relevance.NOTICE,
            reasons=("проверка",),
            bank_card=stale,
        )
        stale_text = explain(company, hidden)
        self.assertIn("Свежей карточки банка по этому фактору нет.", stale_text)
        self.assertNotIn("K6", stale_text)
        self.assertEqual(
            [line for line in stale_text.splitlines() if line.startswith("Вывод модели")],
            ["Вывод модели."],
        )


class CounterpartyReasonTest(unittest.TestCase):
    def test_named_counterparty_at_least_10_percent_is_a_reason(self) -> None:
        item = _item("Ставка для U_big", {Factor.RATE: 3}, summary="и ещё U_exact")
        rows = (
            CounterpartyShare("U_big", 400.0, 5, 0.4),
            CounterpartyShare("U_exact", 100.0, 4, 0.10),
            CounterpartyShare("U_small", 95.0, 1, 0.095),
            CounterpartyShare("U_bigger", 50.0, 1, 0.2),
        )
        reasons = counterparty_reasons(item, rows)
        self.assertEqual(
            reasons,
            (
                "Контрагент U_big, доля 40% платежей: новость про него.",
                "Контрагент U_exact, доля 10% платежей: новость про него.",
            ),
        )

    def test_unnamed_counterparty_stays_out_of_the_ranked_reasons(self) -> None:
        company = CompanyProfile(synthetic_u="h", industry="housing")
        item = _item("Ставка без имени", {Factor.RATE: 3})
        ranked = rank_for_role(
            company,
            [item],
            Role.TREASURER,
            as_of=_AS_OF,
            counterparties=(CounterpartyShare("U_big", 400.0, 5, 0.4),),
        )
        self.assertTrue(ranked)
        self.assertFalse(any("U_big" in reason for reason in ranked[0].reasons))


class WeightSourceTest(unittest.TestCase):
    def test_assumption_covers_every_factor(self) -> None:
        weights = assumed_role_weights()
        treasurer = weights[Role.TREASURER]
        owner = weights[Role.OWNER]
        accountant = weights[Role.CHIEF_ACCOUNTANT]
        for row in weights.values():
            self.assertEqual(set(row), set(Factor))
            self.assertEqual(max(row.values()), 1.0)
        self.assertEqual(treasurer[Factor.RATE], treasurer[Factor.FX])
        self.assertEqual(treasurer[Factor.RATE], treasurer[Factor.DEBT])
        self.assertGreater(treasurer[Factor.RATE], treasurer[Factor.DEMAND])
        self.assertEqual(owner[Factor.DEMAND], 1.0)
        self.assertEqual(owner[Factor.BUDGET], 1.0)
        self.assertEqual(accountant[Factor.LABOR], 1.0)
        self.assertLess(accountant[Factor.BUDGET], owner[Factor.BUDGET])

    def test_workbook_sheet_scales_each_role_by_its_maximum(self) -> None:
        rows: list[list[object]] = [
            ["Фактор", "Казначей", "Главбух", "Собственник"],
            ["F1", 3, 1, 1],
            ["F2", 3, 1, 1],
            ["F4", "1,5", 1, 3],
            ["F5", 1, 3, 1],
            ["F7", 1, 2, 3],
            ["F8", 3, 1, 1],
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weights.xlsx"
            _write_xlsx(path, "Веса ролей", rows)
            loaded = load_role_weights(path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertAlmostEqual(loaded[Role.TREASURER][Factor.RATE], 1.0)
        self.assertAlmostEqual(loaded[Role.TREASURER][Factor.DEMAND], 0.5)
        self.assertEqual(loaded[Role.TREASURER][Factor.LABOR], 1 / 3)
        self.assertEqual(loaded[Role.TREASURER][Factor.INFLATION], 0.0)
        self.assertAlmostEqual(loaded[Role.OWNER][Factor.DEMAND], 1.0)
        self.assertAlmostEqual(loaded[Role.OWNER][Factor.BUDGET], 1.0)
        self.assertAlmostEqual(loaded[Role.CHIEF_ACCOUNTANT][Factor.LABOR], 1.0)
        self.assertAlmostEqual(loaded[Role.CHIEF_ACCOUNTANT][Factor.BUDGET], 2 / 3)

    def test_transposed_sheet_and_a_missing_sheet(self) -> None:
        rows: list[list[object]] = [
            ["Роль", "F1", "F4", "F5", "F7"],
            ["Казначей", 3, 1, 1, 1],
            ["Главбух", 1, 1, 3, 2],
            ["Собственник", 1, 3, 1, 3],
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weights.xlsx"
            _write_xlsx(path, "Веса ролей", rows)
            loaded = load_role_weights(path)
            _write_xlsx(path, "Другой лист", rows)
            missing = load_role_weights(path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertAlmostEqual(loaded[Role.TREASURER][Factor.RATE], 1.0)
        self.assertAlmostEqual(loaded[Role.TREASURER][Factor.DEMAND], 1 / 3)
        self.assertEqual(loaded[Role.TREASURER][Factor.FX], 0.0)
        self.assertIsNone(missing)
        self.assertIsNone(load_role_weights(Path("missing-weights.xlsx")))

    def test_eight_benchmarks_run_only_when_the_workbook_is_present(self) -> None:
        path = find_role_workbook()
        if path is None:
            self.skipTest(
                "Аналитика хакатона Альфа (таблицы).xlsx is absent; "
                "the eight benchmarks were not run"
            )
        names = set(workbook_sheet_names(path))
        benchmark_sheets = {
            "Эталоны",
            "Событие x компания",
            "Событие × компания",
        }
        if not names.intersection(benchmark_sheets):
            self.skipTest(f"{path} has no benchmark sheet")
        self.fail(
            f"{path} has a benchmark sheet, but it is not mapped. "
            "A green suite is not proof on unseen news."
        )


if __name__ == "__main__":
    unittest.main()
