from __future__ import annotations

import unittest

from diff import diff_deleted_domains
from filters import filter_domains
from scorer import score_domain


class CorePipelineTests(unittest.TestCase):
    def test_diff_deleted_domains(self) -> None:
        yesterday = {"alpha.com", "bravo.com", "charlie.com"}
        today = {"alpha.com", "charlie.com"}

        self.assertEqual(diff_deleted_domains(yesterday, today), {"bravo.com"})

    def test_default_filters(self) -> None:
        domains = {
            "flowmint.com",
            "abc.com",
            "my-domain.com",
            "brand123.com",
            "rhythm.com",
            "zzzzflow.com",
            "validname.net",
        }

        self.assertEqual(filter_domains(domains), ["flowmint.com"])

    def test_score_domain_rewards_brandable_name(self) -> None:
        score = score_domain("flowmint.com")

        self.assertGreaterEqual(score.total_score, 70)
        self.assertIn("short", score.reasons)
        self.assertIn("two-word", score.reasons)


if __name__ == "__main__":
    unittest.main()
