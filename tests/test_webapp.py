import unittest
from pathlib import Path

from config import OUTPUT_DIR
from webapp import _to_output_url


class OutputUrlTests(unittest.TestCase):
    def test_relative_path_inside_output_dir(self) -> None:
        output_root = Path(OUTPUT_DIR)
        self.assertEqual(_to_output_url(str(output_root / "a.png")), "/outputs/a.png")

    def test_absolute_path_inside_output_dir(self) -> None:
        output_root = Path(OUTPUT_DIR).resolve()
        self.assertEqual(_to_output_url(str(output_root / "nested" / "a.png")), "/outputs/nested/a.png")

    def test_path_outside_output_dir_returns_empty(self) -> None:
        self.assertEqual(_to_output_url("/tmp/not-in-output.png"), "")

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(_to_output_url(""), "")


if __name__ == "__main__":
    unittest.main()
