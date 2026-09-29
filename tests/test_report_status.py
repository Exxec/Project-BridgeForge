"""ROADMAP P15 item 31.4: one reader for a revival report's status line."""
import unittest

from bridgeforge.report_status import last_status


class ReportStatusTests(unittest.TestCase):
    def test_last_known_status_bold_or_bare(self) -> None:
        self.assertEqual(last_status("# R\n\nREADY_FOR_LIVE_TEST\n\nmore\n\nLIVE_VALIDATED\n"), "LIVE_VALIDATED")
        self.assertEqual(last_status("## Status\n\n**READY_FOR_LIVE_TEST**\n"), "READY_FOR_LIVE_TEST")
        self.assertEqual(last_status("NOT_A_STATUS\nSUPERSEDED\n"), "SUPERSEDED")

    def test_unknown_capitals_and_inline_mentions_do_not_count(self) -> None:
        self.assertIsNone(last_status("MANUAL\nThe report said READY_FOR_LIVE_TEST earlier.\n"))


if __name__ == "__main__":
    unittest.main()
