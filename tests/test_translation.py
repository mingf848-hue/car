import unittest

from app.translation import translate_market, translate_outcome


class TranslationTests(unittest.TestCase):
    def test_sports_slug_is_rendered_in_chinese(self):
        title = translate_market("mlb-bos-nyy-2026-06-06-total-6pt5", "")

        self.assertEqual(title, "MLB 波士顿红袜 vs 纽约扬基｜总分 6.5｜2026/06/06")

    def test_spread_slug_and_outcome_are_translated(self):
        title = translate_market("mlb-nym-sd-2026-06-06-spread-home-1pt5", "")

        self.assertIn("主队让分 1.5", title)
        self.assertEqual(translate_outcome("New York Mets"), "纽约大都会")
        self.assertEqual(translate_outcome("Under"), "小分")


if __name__ == "__main__":
    unittest.main()
