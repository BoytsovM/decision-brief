"""Selective counterparty list. Reads the small fixtures, not the full payment file."""

from __future__ import annotations

import unittest
from pathlib import Path

from decision_brief.counterparties import counterparties_for_company

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_COMPANIES = _FIXTURES / "companies_small.csv"
_PAYMENTS = _FIXTURES / "payments_small.csv"


class CounterpartyListTest(unittest.TestCase):
    def test_keeps_only_links_of_at_least_10_percent_inside_the_directory(self) -> None:
        rows = counterparties_for_company("U_focal", _PAYMENTS, _COMPANIES)
        self.assertEqual([row.counterparty_id for row in rows], ["U_big", "U_exact"])

        big, exact = rows
        self.assertEqual(big.amount_rub, 400)
        self.assertEqual(big.payment_count, 5)
        self.assertAlmostEqual(big.share, 0.4)

        self.assertEqual(exact.amount_rub, 100)
        self.assertEqual(exact.payment_count, 4)
        self.assertAlmostEqual(exact.share, 0.1)

        self.assertFalse(hasattr(big, "trade_direction"))

    def test_company_outside_the_directory_has_no_counterparties(self) -> None:
        rows = counterparties_for_company("U_outsider", _PAYMENTS, _COMPANIES)
        self.assertEqual(rows, [])

    def test_directory_company_without_payments_has_no_counterparties(self) -> None:
        rows = counterparties_for_company("U_lonely", _PAYMENTS, _COMPANIES)
        self.assertEqual(rows, [])
