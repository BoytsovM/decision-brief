"""Screen feed: company and role change the list, the model block stays empty."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from decision_brief.models import CompanyProfile, Factor, NewsItem
from decision_brief.roles import Role
from decision_brief.screen import (
    NewsLoad,
    card_blocks,
    card_view,
    companies_source_label,
    company_labels,
    csv_fields_raising_score,
    default_companies_path,
    empty_feed_message,
    load_demo_companies,
    load_news,
    markdown_block,
    rank_feed,
    resolve_companies_path,
    retain_feed,
    rss_failure_message,
    sample_companies_path,
    source_link_html,
)

_AS_OF = date(2026, 10, 21)
_PUBLISHED = date(2026, 9, 11)
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_RSS = _FIXTURES / "rss"

_BLOCK_TITLES = (
    "Что произошло",
    "Почему этой компании",
    "Последствия",
    "Как оценивает банк",
    "Вывод модели",
    "Источник",
)


def _item(
    title: str,
    factors: dict[Factor, int],
    *,
    url: str | None = None,
) -> NewsItem:
    return NewsItem(
        title=title,
        published_on=_PUBLISHED,
        source_name="test",
        source_url=url or f"https://example.test/{title}",
        factors=factors,
    )


def _carrier() -> CompanyProfile:
    return CompanyProfile(
        synthetic_u="U_3263",
        industry="transport",
        okved="49.41",
        revenue_rub=32_300_000_000,
        has_leasing=True,
        staff_over_100=True,
    )


class ScreenFeedTests(unittest.TestCase):
    """Composition follows the company. Order follows the role."""

    def test_role_changes_order(self) -> None:
        company = CompanyProfile("h", "housing")
        items = [
            _item("rate", {Factor.RATE: 3}),
            _item("demand", {Factor.DEMAND: 3}),
        ]
        treasurer = rank_feed(company, items, Role.TREASURER, as_of=_AS_OF)
        owner = rank_feed(company, items, Role.OWNER, as_of=_AS_OF)
        self.assertEqual([row.item.title for row in treasurer], ["rate", "demand"])
        self.assertEqual([row.item.title for row in owner], ["demand", "rate"])
        self.assertGreater(treasurer[0].score, treasurer[1].score)
        self.assertGreater(owner[0].score, owner[1].score)

    def test_company_changes_composition(self) -> None:
        items = [_item("rate", {Factor.RATE: 3})]
        shown = rank_feed(_carrier(), items, Role.TREASURER, as_of=_AS_OF)
        hidden = rank_feed(
            CompanyProfile("demo-horeca", "horeca", okved="56.10"),
            items,
            Role.TREASURER,
            as_of=_AS_OF,
        )
        self.assertEqual([row.item.title for row in shown], ["rate"])
        self.assertEqual(hidden, [])

    def test_old_news_is_below_the_threshold(self) -> None:
        item = NewsItem(
            title="old",
            published_on=date(2021, 1, 1),
            source_name="t",
            source_url="https://example.test/old",
            factors={Factor.RATE: 3},
        )
        ranked = rank_feed(
            CompanyProfile("h", "housing"),
            [item],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        self.assertEqual(ranked, [])
        self.assertEqual(empty_feed_message(), "Нет новостей выше порога.")


class CardTests(unittest.TestCase):
    """Six blocks. The model line is empty unless a client is passed in."""

    def _shown(self):
        items = [_item("rate", {Factor.RATE: 3}, url="https://example.test/rate")]
        return rank_feed(_carrier(), items, Role.TREASURER, as_of=_AS_OF)

    def test_blocks_bank_link_and_empty_model(self) -> None:
        shown = self._shown()
        view = card_view(
            _carrier(),
            shown[0],
            role=Role.TREASURER,
            client=None,
            shown=shown,
        )
        titles = tuple(title for title, _body in card_blocks(view))
        self.assertEqual(titles, _BLOCK_TITLES)
        self.assertEqual(view.model, "")
        self.assertIn("14,0", view.bank)
        self.assertNotIn("14,0", view.model)
        self.assertIn("лизинг", view.consequences)
        self.assertIn("CL_PRODUCT_LEA_MARK", view.csv_fields_line())
        self.assertNotIn("AMOUNT_WORKERS_FNS_GRADATION", view.csv_fields)
        link = source_link_html(view.source_name, view.source_url)
        self.assertIn('href="https://example.test/rate"', link)
        self.assertIn("<a ", link)

    def test_model_text_stays_out_of_the_bank_block(self) -> None:
        shown = self._shown()

        class _Client:
            def complete(self, prompt: str) -> str:
                return (
                    '{"последствия": "Пауза сохранится.", '
                    '"риск": "Платеж останется дорогим.", '
                    '"возможность": "Новых действий нет.", '
                    '"что проверить": "Срок паузы."}'
                )

        view = card_view(
            _carrier(),
            shown[0],
            role=Role.TREASURER,
            client=_Client(),
            shown=shown,
        )
        self.assertIn("Пауза сохранится", view.model)
        self.assertNotIn("Пауза сохранится", view.bank)
        self.assertIn("14,0", view.bank)
        self.assertNotIn("14,0", view.model)

    def test_non_http_source_is_not_a_link(self) -> None:
        rendered = source_link_html("банк", "javascript:alert(1)")
        self.assertNotIn("<a ", rendered)
        self.assertIn("javascript:alert(1)", rendered)

    def test_quote_in_url_is_escaped(self) -> None:
        rendered = source_link_html("n", 'https://example.test/a"b')
        self.assertIn('href="https://example.test/a&quot;b"', rendered)

    def test_happened_drops_feed_markup(self) -> None:
        company = _carrier()
        item = NewsItem(
            title="Ставки <!-- TypographyUse -->",
            published_on=_PUBLISHED,
            source_name="Банк России",
            source_url="https://example.test/cbr",
            summary="Текст <b>ставки</b> &amp; пауза.",
            factors={Factor.RATE: 3},
        )
        shown = rank_feed(company, [item], Role.TREASURER, as_of=_AS_OF)
        view = card_view(
            company,
            shown[0],
            role=Role.TREASURER,
            client=None,
            shown=shown,
        )
        self.assertNotIn("<!--", view.happened)
        self.assertNotIn("<b>", view.happened)
        self.assertNotIn("&amp;", view.happened)
        self.assertIn("ставки", view.happened)
        self.assertIn("&", view.happened)

    def test_markdown_block_keeps_stars_literal(self) -> None:
        rendered = markdown_block("a *b*\nс")
        self.assertIn("\\*b\\*", rendered)
        self.assertIn("  \n", rendered)


class CsvFieldTests(unittest.TestCase):
    """A column is listed only when it actually lifts this item's exposure."""

    def test_each_single_flag_names_its_column(self) -> None:
        cases = (
            (dict(has_loan=True), {Factor.RATE: 3}, "CL_PRODUCT_LOA_MARK"),
            (dict(has_leasing=True), {Factor.RATE: 3}, "CL_PRODUCT_LEA_MARK"),
            (dict(has_factoring=True), {Factor.RATE: 3}, "FACTORING_MARK"),
            (dict(has_deposit=True), {Factor.RATE: 3}, "CL_PRODUCT_DEP_MARK"),
            (dict(rapid_growth=True), {Factor.RATE: 3}, "ECO_MARK_LABEL"),
            (dict(has_foreign_trade=True), {Factor.FX: 3}, "FTS_FLAG"),
            (dict(foreign_owner=True), {Factor.FX: 3}, "OKFS_NAME"),
            (dict(has_guarantee=True), {Factor.BUDGET: 3}, "CL_PRODUCT_GAR_MARK"),
        )
        for flags, factors, column in cases:
            company = CompanyProfile("u", "services", **flags)
            item = _item(column, factors)
            with self.subTest(column=column):
                self.assertEqual(csv_fields_raising_score(company, item), (column,))

    def test_second_rate_flag_stops_at_the_cap(self) -> None:
        company = CompanyProfile("u", "transport", has_loan=True, has_leasing=True)
        fields = csv_fields_raising_score(company, _item("rate", {Factor.RATE: 3}))
        self.assertEqual(fields, ("CL_PRODUCT_LOA_MARK",))

    def test_housing_rate_is_already_at_the_cap(self) -> None:
        company = CompanyProfile("u", "housing", has_loan=True, has_leasing=True)
        item = _item("rate", {Factor.RATE: 3})
        fields = csv_fields_raising_score(company, item)
        self.assertEqual(fields, ())
        shown = rank_feed(company, [item], Role.OWNER, as_of=_AS_OF)
        view = card_view(
            company,
            shown[0],
            role=Role.OWNER,
            client=None,
            shown=shown,
        )
        self.assertEqual(view.csv_fields_line(), "Поля CSV скор не поднимали.")

    def test_unrelated_flag_is_not_listed(self) -> None:
        company = CompanyProfile("u", "services", has_loan=True)
        fields = csv_fields_raising_score(company, _item("demand", {Factor.DEMAND: 3}))
        self.assertEqual(fields, ())

    def test_labor_columns_share_one_bump(self) -> None:
        company = CompanyProfile(
            "u",
            "transport",
            has_payroll=True,
            staff_over_100=True,
        )
        fields = csv_fields_raising_score(company, _item("labor", {Factor.LABOR: 3}))
        self.assertEqual(
            fields,
            ("CL_PRODUCT_ZPP_MARK", "AMOUNT_WORKERS_FNS_GRADATION"),
        )

    def test_payroll_alone(self) -> None:
        company = CompanyProfile("u", "transport", has_payroll=True)
        fields = csv_fields_raising_score(company, _item("labor", {Factor.LABOR: 3}))
        self.assertEqual(fields, ("CL_PRODUCT_ZPP_MARK",))

    def test_labor_at_cap_lists_nothing(self) -> None:
        company = CompanyProfile("u", "horeca", staff_over_100=True)
        fields = csv_fields_raising_score(company, _item("labor", {Factor.LABOR: 3}))
        self.assertEqual(fields, ())

    def test_china_raises_commodity_only_for_those_industries(self) -> None:
        item = _item("metal", {Factor.COMMODITY: 3})
        metals = CompanyProfile("m", "metals", foreign_trade_countries="КИТАЙ")
        retail = CompanyProfile("r", "retail", foreign_trade_countries="КИТАЙ")
        self.assertEqual(csv_fields_raising_score(metals, item), ("FTS_COUNTRY_NAME",))
        self.assertEqual(csv_fields_raising_score(retail, item), ())


class RssRetentionTests(unittest.TestCase):
    """A failed refresh does not drop a feed that was already computed."""

    def test_partial_failure_replaces_the_feed(self) -> None:
        gazeta = (_RSS / "gazeta_rate_credit.xml").read_text(encoding="utf-8")

        def fetcher(url: str) -> str:
            if "down" in url:
                raise OSError("down")
            return gazeta

        loaded = load_news(
            (
                "https://down.example/rss",
                "https://www.gazeta.ru/export/rss/business.xml",
            ),
            fetcher=fetcher,
        )
        self.assertFalse(loaded.failed)
        self.assertEqual(loaded.items[0].source_name, "Газета.Ru")
        previous = [_item("old", {Factor.RATE: 3}, url="https://example.test/old")]
        kept, show_error = retain_feed(previous, loaded)
        self.assertFalse(show_error)
        self.assertEqual(kept[0].source_name, "Газета.Ru")

    def test_total_failure_keeps_the_previous_feed(self) -> None:
        def fetcher(url: str) -> str:
            raise OSError("down")

        loaded = load_news(
            ("https://down.example/a", "https://down.example/b"),
            fetcher=fetcher,
        )
        self.assertTrue(loaded.failed)
        self.assertEqual(loaded.items, ())
        previous = [_item("kept", {Factor.RATE: 3}, url="https://example.test/kept")]
        kept, show_error = retain_feed(previous, loaded)
        self.assertTrue(show_error)
        self.assertEqual(kept[0].source_url, "https://example.test/kept")
        self.assertIn("уже посчитанная", rss_failure_message(kept_previous=True))

    def test_broken_xml_is_a_failure(self) -> None:
        loaded = load_news(
            ("https://www.interfax.ru/rss",),
            fetcher=lambda url: "<rss",
        )
        self.assertTrue(loaded.failed)
        self.assertEqual(loaded.items, ())

    def test_valid_empty_feed_is_not_a_failure(self) -> None:
        xml = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        loaded = load_news(
            ("https://www.cbr.ru/rss/eventrss",),
            fetcher=lambda url: xml,
        )
        self.assertFalse(loaded.failed)
        previous = [_item("old", {Factor.RATE: 3})]
        kept, show_error = retain_feed(previous, loaded)
        self.assertFalse(show_error)
        self.assertEqual(kept, [])

    def test_first_failure_has_nothing_to_keep(self) -> None:
        kept, show_error = retain_feed([], NewsLoad((), True))
        self.assertEqual(kept, [])
        self.assertTrue(show_error)
        message = rss_failure_message(kept_previous=False)
        self.assertNotIn("уже посчитанная", message)
        self.assertIn("не загрузилась", message)


class DemoSetTests(unittest.TestCase):
    """The selector reads the chat-1 demo set, not a second profile list."""

    def test_fixture_demo_is_the_large_carrier(self) -> None:
        demo = load_demo_companies(_FIXTURES / "brief_companies.csv")
        self.assertEqual([company.synthetic_u for company in demo], ["U_focal"])

    def test_duplicate_labels_stay_distinct(self) -> None:
        company = CompanyProfile(
            "U_1",
            "transport",
            okved="49.41",
            revenue_rub=16_000_000_000,
        )
        labels = company_labels([company, company])
        self.assertNotEqual(labels[0][0], labels[1][0])
        self.assertTrue(labels[1][0].endswith("#2"))

    def test_default_path_points_at_raw_csv(self) -> None:
        path = default_companies_path()
        self.assertEqual(path.name, "df_Uid_data_hack.csv")
        self.assertEqual(path.parent.name, "raw")


class SampleCompaniesTests(unittest.TestCase):
    """The committed CSV is enough for the screen when the full file is absent."""

    def test_sample_demo_set(self) -> None:
        demo = load_demo_companies(sample_companies_path())
        self.assertEqual(
            [company.synthetic_u for company in demo],
            ["U_sample_transport", "U_sample_horeca", "U_sample_housing"],
        )

    def test_sample_clients_do_not_share_a_rate_feed(self) -> None:
        demo = {
            company.synthetic_u: company
            for company in load_demo_companies(sample_companies_path())
        }
        item = _item("rate", {Factor.RATE: 3})
        transport = rank_feed(
            demo["U_sample_transport"],
            [item],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        housing = rank_feed(
            demo["U_sample_housing"],
            [item],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        horeca = rank_feed(
            demo["U_sample_horeca"],
            [item],
            Role.TREASURER,
            as_of=_AS_OF,
        )
        self.assertEqual([row.item.title for row in transport], ["rate"])
        self.assertEqual([row.item.title for row in housing], ["rate"])
        self.assertEqual(horeca, [])

    def test_missing_raw_selects_the_sample(self) -> None:
        missing = Path("data/raw/not-in-the-repo.csv")
        sample = sample_companies_path()
        chosen = resolve_companies_path(environ={}, raw=missing, sample=sample)
        self.assertEqual(chosen, sample)
        self.assertIn("Синтетический", companies_source_label(sample))

    def test_existing_raw_wins_over_the_sample(self) -> None:
        raw = sample_companies_path()
        chosen = resolve_companies_path(
            environ={},
            raw=raw,
            sample=Path("data/sample/unused.csv"),
        )
        self.assertEqual(chosen, raw)

    def test_env_override_points_at_the_given_file(self) -> None:
        chosen = resolve_companies_path(
            environ={"DECISION_BRIEF_COMPANIES": "custom/companies.csv"},
            raw=sample_companies_path(),
            sample=Path("data/sample/unused.csv"),
        )
        self.assertEqual(chosen, Path("custom/companies.csv"))
        label = companies_source_label(chosen)
        self.assertIn("companies.csv", label)
        self.assertIn("custom", label)

    def test_raw_label_names_the_gitignored_file(self) -> None:
        label = companies_source_label(default_companies_path())
        self.assertIn("data/raw/df_Uid_data_hack.csv", label)
        self.assertIn("git", label)


if __name__ == "__main__":
    unittest.main()
