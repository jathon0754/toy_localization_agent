import unittest

from market_normalizer import normalize_market


class MarketNormalizerTests(unittest.TestCase):
    def test_alias_mapping(self) -> None:
        result = normalize_market("USA", available=["usa", "japan"])
        self.assertEqual(result.normalized, "usa")
        self.assertEqual(result.confidence, "high")

    def test_chinese_city_mapping(self) -> None:
        result = normalize_market("漳州", available=["cn"])
        self.assertEqual(result.normalized, "cn")
        self.assertTrue(result.notes)

    def test_region_specific_mapping(self) -> None:
        result = normalize_market("福建", available=["cn-fujian"])
        self.assertEqual(result.normalized, "cn-fujian")


if __name__ == "__main__":
    unittest.main()
