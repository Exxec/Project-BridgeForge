"""Resource locations must retain their meaning when source modules move."""
from pathlib import Path
import unittest

from bridgeforge.atlas import atlas_predictions


class RefactorResourceTests(unittest.TestCase):
    def test_atlas_predictions_still_uses_the_repo_docs_file(self) -> None:
        expected = Path(__file__).resolve().parent.parent / "docs" / "atlas_predictions.json"
        self.assertEqual(atlas_predictions.DEFAULT_PATH, expected)
        self.assertTrue(expected.is_file())
