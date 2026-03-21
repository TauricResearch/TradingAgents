import unittest

from cli.utils import CUSTOM_OPENROUTER_MODEL, resolve_model_choice


class OpenRouterModelSelectionTests(unittest.TestCase):
    def test_builtin_model_is_returned_unchanged(self):
        self.assertEqual(
            resolve_model_choice("openrouter", "z-ai/glm-4.5-air:free", "Quick-Thinking"),
            "z-ai/glm-4.5-air:free",
        )

    def test_custom_model_prompt_value_is_trimmed(self):
        chosen = resolve_model_choice(
            "openrouter",
            CUSTOM_OPENROUTER_MODEL,
            "Deep-Thinking",
            prompt_fn=lambda _: " minimax/minimax-m2.1 ",
        )
        self.assertEqual(chosen, "minimax/minimax-m2.1")

    def test_exit_on_no_choice(self):
        with self.assertRaises(SystemExit) as cm:
            resolve_model_choice("openrouter", None, "Quick-Thinking")
        self.assertEqual(cm.exception.code, 1)

    def test_exit_on_empty_custom_model_input(self):
        with self.assertRaises(SystemExit) as cm:
            resolve_model_choice(
                "openrouter",
                CUSTOM_OPENROUTER_MODEL,
                "Deep-Thinking",
                prompt_fn=lambda _: "   ",
            )
        self.assertEqual(cm.exception.code, 1)

    def test_exit_on_none_custom_model_input(self):
        with self.assertRaises(SystemExit) as cm:
            resolve_model_choice(
                "openrouter",
                CUSTOM_OPENROUTER_MODEL,
                "Deep-Thinking",
                prompt_fn=lambda _: None,
            )
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
