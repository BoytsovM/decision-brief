"""Company demo set, group rollup, and OKVED spelling. No network."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from decision_brief.companies import (
    is_demo_candidate,
    load_companies,
    select_demo_companies,
    summarize_groups,
)
from decision_brief.industries import industry_for_okved, normalize_okved
from decision_brief.models import CompanyProfile

_THRESHOLD_RUB = 15_000_000_000


class OkvedNormalizationTest(unittest.TestCase):
    def test_short_and_zero_padded_group_are_one_code(self) -> None:
        self.assertEqual(normalize_okved("41.2"), normalize_okved("41.20"))
        self.assertEqual(normalize_okved("41,20"), normalize_okved("41.2"))
        canonical = normalize_okved("41.20")
        self.assertEqual(industry_for_okved(canonical), "housing")
        self.assertEqual(industry_for_okved("41.2"), industry_for_okved("41.20"))

    def test_parent_subclass_is_not_rewritten_into_a_zero_group(self) -> None:
        self.assertEqual(normalize_okved("49.4"), "49.4")
        self.assertNotEqual(normalize_okved("49.4"), normalize_okved("49.41"))
        self.assertEqual(normalize_okved("01.11"), "01.11")


class DemoRevenueTest(unittest.TestCase):
    def test_own_revenue_of_15_billion_is_the_company_gate(self) -> None:
        below = CompanyProfile(
            synthetic_u="U_small",
            industry="services",
            revenue_rub=_THRESHOLD_RUB - 1,
        )
        exact = CompanyProfile(
            synthetic_u="U_large",
            industry="services",
            revenue_rub=_THRESHOLD_RUB,
        )
        self.assertFalse(is_demo_candidate(below))
        self.assertTrue(is_demo_candidate(exact))
        self.assertEqual(select_demo_companies([below, exact]), [exact])

    def test_repeated_synthetic_id_stays_out_of_the_demo_set(self) -> None:
        repeated = CompanyProfile(
            synthetic_u="U_428697",
            industry="wholesale",
            revenue_rub=_THRESHOLD_RUB + 1,
        )
        self.assertTrue(is_demo_candidate(repeated))
        self.assertEqual(select_demo_companies([repeated]), [])


class GroupRollupTest(unittest.TestCase):
    def test_group_sum_is_not_the_demo_rule(self) -> None:
        path = _write_companies(
            self,
            [
                ("U_a", "41.2", 10_000_000_000, "g_split"),
                ("U_b", "41.20", 10_000_000_000, "g_split"),
                ("U_428697", "46.90", 20_000_000_000, "g_repeat"),
                ("U_big", "49.41", 16_000_000_000, "g_one"),
                ("U_tiny", "56.10", 1_000_000_000, "g_small"),
            ],
        )
        companies = load_companies(path)
        by_id = {company.synthetic_u: company for company in companies}
        self.assertEqual(by_id["U_a"].okved, by_id["U_b"].okved)
        self.assertEqual(by_id["U_a"].industry, "housing")

        demo_ids = [company.synthetic_u for company in select_demo_companies(companies)]
        self.assertEqual(demo_ids, ["U_big"])

        groups = {group.group_id: group for group in summarize_groups(path)}
        split = groups["g_split"]
        self.assertEqual(split.legal_entity_count, 2)
        self.assertEqual(split.revenue_rub, 20_000_000_000)
        self.assertTrue(split.passes_large_revenue)
        self.assertTrue(groups["g_repeat"].passes_large_revenue)
        self.assertTrue(groups["g_one"].passes_large_revenue)
        self.assertFalse(groups["g_small"].passes_large_revenue)
        self.assertEqual(groups["g_one"].legal_entity_count, 1)


def _write_companies(
    test: unittest.TestCase,
    rows: list[tuple[str, str, int, str]],
) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="companies_"))
    test.addCleanup(lambda: _remove_tree(folder))
    path = folder / "companies.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "SYNTHETIC_U",
                "MAINOKVED_CODE",
                "REVENUE_COMPANY",
                "GROUP_ID",
            ],
            delimiter=";",
        )
        writer.writeheader()
        for synthetic_u, okved, revenue, group_id in rows:
            writer.writerow(
                {
                    "SYNTHETIC_U": synthetic_u,
                    "MAINOKVED_CODE": okved,
                    "REVENUE_COMPANY": str(revenue),
                    "GROUP_ID": group_id,
                }
            )
    return path


def _remove_tree(folder: Path) -> None:
    for child in folder.iterdir():
        child.unlink()
    folder.rmdir()
