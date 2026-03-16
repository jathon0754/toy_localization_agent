import unittest

from knowledge.retriever import CountryKnowledgeRetriever


class CountryKnowledgeRetrieverTests(unittest.TestCase):
    def test_missing_market_file_falls_back_to_generic_reference(self) -> None:
        retriever = CountryKnowledgeRetriever("unknown-market")
        reference = retriever.get_reference("robot toy")
        self.assertIn("No local knowledge file found", reference)

    def test_invalid_market_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CountryKnowledgeRetriever("../japan")

    def test_known_market_file_is_loaded(self) -> None:
        retriever = CountryKnowledgeRetriever("japan")
        reference = retriever.get_reference("robot toy")
        self.assertTrue(reference.strip())
        self.assertIn("Metadata:", reference)
        self.assertIn("last_updated", reference)


if __name__ == "__main__":
    unittest.main()
