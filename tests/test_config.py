import tempfile
import unittest
from unittest.mock import patch

from config import resolve_run_output_dir, sanitize_run_id


class ConfigOutputDirTests(unittest.TestCase):
    def test_sanitize_run_id(self) -> None:
        self.assertEqual(sanitize_run_id("../bad"), "bad")
        self.assertEqual(sanitize_run_id(""), "run")

    def test_resolve_run_output_dir_creates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("config.OUTPUT_DIR", tmp):
                path = resolve_run_output_dir("job:1")
                self.assertTrue(path.exists())
                self.assertIn(tmp, str(path))


if __name__ == "__main__":
    unittest.main()
