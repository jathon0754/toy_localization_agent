import unittest

from schemas import (
    CULTURE_SPEC,
    CultureOutput,
    has_substantive_content,
    normalize_payload,
    validate_model,
)


class SchemaNormalizationTests(unittest.TestCase):
    def test_normalize_and_validate(self) -> None:
        raw = {"colors": "red; blue", "communication_style": 123}
        normalized = normalize_payload(raw, CULTURE_SPEC)
        self.assertEqual(normalized["colors"], ["red", "blue"])
        self.assertEqual(normalized["communication_style"], "123")

        validated, err = validate_model(CultureOutput, normalized)
        self.assertIsNone(err)
        self.assertEqual(validated["colors"], ["red", "blue"])

    def test_has_substantive_content(self) -> None:
        normalized = normalize_payload({}, CULTURE_SPEC)
        self.assertFalse(has_substantive_content(normalized, CULTURE_SPEC))


if __name__ == "__main__":
    unittest.main()
