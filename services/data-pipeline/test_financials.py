import unittest
from dataclasses import replace

from financials import calculate, detect
from mock_source import MockAnnualAdapter


class FinancialsTest(unittest.TestCase):
    def setUp(self):
        self.profiles = list(MockAnnualAdapter().read())
        self.statements = self.profiles[0][1]

    def test_calculates_comparable_periods_and_units(self):
        history = calculate(self.statements)
        self.assertNotIn("revenue_yoy", history[2016])
        self.assertNotIn("roe", history[2016])
        self.assertAlmostEqual(history[2025]["revenue_yoy"], (620 / 520 - 1) * 100, places=4)
        self.assertEqual(history[2025]["net_margin"], 25)
        self.assertEqual(history[2025]["debt_ratio"], 50)
        self.assertLess(history[2025]["free_cash"], history[2025]["operating_cash"])

    def test_missing_period_and_fields_remain_missing(self):
        history = calculate(self.statements[0:3:2])
        self.assertNotIn("revenue_yoy", history[2018])
        for values in calculate(self.profiles[-1][1]).values():
            self.assertNotIn("gross_margin", values)
            self.assertNotIn("free_cash", values)

    def test_rejects_invalid_input(self):
        for statement in (replace(self.statements[0], currency="USD"),
                          replace(self.statements[0], revenue=float("nan")),
                          replace(self.statements[0], liabilities=100000)):
            with self.assertRaises(ValueError):
                calculate([statement])
        with self.assertRaises(ValueError):
            calculate([self.statements[0], self.statements[0]])

    def test_demo_triggers_all_rules_with_evidence(self):
        rules = set()
        for _, statements in self.profiles:
            history = calculate(statements)
            last = max(history)
            for rule, metric, _, _, _, _, evidence, years in detect(history):
                rules.add(rule)
                self.assertIn(metric, evidence)
                for year in range(last - years + 1, last + 1):
                    for key in evidence:
                        self.assertIn(key, history[year])
        self.assertEqual(rules, {"R1", "R2", "R3", "R4", "R5"})


if __name__ == "__main__":
    unittest.main()
