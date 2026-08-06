import unittest

from src.services.led_preview import PreviewRefreshState


class PreviewRefreshStateTests(unittest.TestCase):
    def test_preview_starts_only_after_explicit_request(self):
        state = PreviewRefreshState()

        self.assertFalse(state.running)
        self.assertFalse(state.has_preview)
        self.assertEqual(state.button_label, "生成预览")

        token = state.begin()

        self.assertEqual(token, 0)
        self.assertTrue(state.running)
        self.assertEqual(state.button_label, "正在生成…")

    def test_edit_before_first_preview_keeps_generate_label(self):
        state = PreviewRefreshState()

        state.mark_dirty()

        self.assertTrue(state.dirty)
        self.assertEqual(state.button_label, "生成预览")

    def test_edit_during_render_marks_completed_preview_as_stale(self):
        state = PreviewRefreshState()
        token = state.begin()

        state.mark_dirty()
        stale = state.complete(token, success=True)

        self.assertTrue(stale)
        self.assertTrue(state.has_preview)
        self.assertTrue(state.dirty)
        self.assertEqual(state.button_label, "重新生成预览")

    def test_matching_completion_clears_dirty_state(self):
        state = PreviewRefreshState()
        state.mark_dirty()
        token = state.begin()

        stale = state.complete(token, success=True)

        self.assertFalse(stale)
        self.assertTrue(state.has_preview)
        self.assertFalse(state.dirty)
        self.assertEqual(state.button_label, "重新生成预览")


if __name__ == "__main__":
    unittest.main()
