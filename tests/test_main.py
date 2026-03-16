import unittest
from unittest.mock import patch

from main import should_generate_3d


class ShouldGenerate3DTests(unittest.TestCase):
    def test_auto_3d_true_skips_prompt(self) -> None:
        with patch("builtins.input") as mocked_input:
            self.assertTrue(should_generate_3d(auto_3d=True))
            mocked_input.assert_not_called()

    def test_user_confirms_generation(self) -> None:
        with patch("builtins.input", return_value="y"):
            self.assertTrue(should_generate_3d(auto_3d=False))

    def test_user_declines_generation(self) -> None:
        with patch("builtins.input", return_value="n"):
            self.assertFalse(should_generate_3d(auto_3d=False))

    def test_non_interactive_defaults_to_skip(self) -> None:
        with patch("builtins.input", side_effect=EOFError), patch("builtins.print"):
            self.assertFalse(should_generate_3d(auto_3d=False))


if __name__ == "__main__":
    unittest.main()
