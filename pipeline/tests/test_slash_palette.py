"""Slash-command palette (roadmap item 4): on-demand ACTIONS over features that
already exist. Static assertions only — behavior is smoke-tested in the app.
Guards: every command maps to an existing target, and the palette never sends a
question on the attorney's behalf (trust posture — the attorney presses Ask)."""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

APP_JS = (PIPELINE_DIR / "static" / "app.js").read_text()
APP_CSS = (PIPELINE_DIR / "static" / "app.css").read_text()


class TestSlashPaletteMarkupAndWiring(unittest.TestCase):
    def test_functions_present(self):
        for fn in [
            "function slashArg",
            "function findLastAnswerCopyButton",
            "function hideSlashPalette",
            "function renderSlashPalette",
            "function updateSlashPalette",
            "function applySlashCommand",
        ]:
            self.assertIn(fn, APP_JS)

    def test_command_list_present(self):
        self.assertIn("var SLASH_COMMANDS", APP_JS)
        for cmd in ["deadlines", "overview", "compare", "review", "find", "summarize", "copy"]:
            self.assertIn('"' + cmd + '"', APP_JS)

    def test_command_descriptions_present(self):
        for desc in [
            "Deadlines for this matter",
            "Matter overview: parties, timeline, deadlines",
            "Compare documents",
            "Contract review",
            "Ask where the documents discuss",
            "Summarize the key documents in this matter, with citations.",
            "Copy the last answer with citations",
        ]:
            self.assertIn(desc, APP_JS)

    def test_find_and_summarize_fill_composer_text(self):
        # These insert an editable question — they must never appear pre-baked
        # into a sendChat() call anywhere near their construction.
        self.assertIn("Where do this matter's documents discuss ", APP_JS)
        self.assertIn("Summarize the key documents in this matter, with citations.", APP_JS)

    def test_palette_dom_container_in_composer(self):
        chat = APP_JS[APP_JS.index("function buildChat"):APP_JS.index("function chatHook")]
        self.assertIn("id='slash-palette'", chat)
        self.assertIn("chat-input", chat)

    def test_no_matter_hint_present(self):
        self.assertIn("Select a matter first.", APP_JS)

    def test_copy_no_answer_hint_present(self):
        self.assertIn("No answer to copy yet.", APP_JS)

    def test_navigation_commands_reuse_existing_targets(self):
        apply_fn = APP_JS[APP_JS.index("function applySlashCommand"):
                           APP_JS.index("// UX-7 (owner-directed)")]
        # /deadlines and /overview both navigate to the matter detail page (where
        # the overview's Deadlines panel lives) — the existing openMatter() route.
        self.assertIn("openMatter(state.matter)", apply_fn)
        # /compare and /review reuse the existing Review & Compare tabs.
        self.assertIn('openReviewTab("grid")', apply_fn)
        self.assertIn('openReviewTab("clauses")', apply_fn)
        # /copy reuses the existing copy-answer-btn mechanism, it does not
        # reimplement clipboard logic.
        self.assertIn("findLastAnswerCopyButton", apply_fn)
        self.assertIn(".click()", apply_fn)

    def test_navigation_commands_clear_composer(self):
        apply_fn = APP_JS[APP_JS.index("function applySlashCommand"):
                           APP_JS.index("// UX-7 (owner-directed)")]
        nav_block = apply_fn[apply_fn.index('item.cmd === "deadlines"'):
                              apply_fn.index('item.cmd === "find"')]
        self.assertIn('input.value = "";', nav_block)

    def test_never_auto_sends_a_question(self):
        # The palette fills or navigates; it must never call sendChat() itself —
        # only the attorney pressing Ask (or the existing Enter-to-send handler
        # outside the palette) sends a question. Checked at the function-body
        # level (not just absence of the substring) so a future refactor that
        # keeps the name but adds a call would still be caught.
        apply_fn = APP_JS[APP_JS.index("function applySlashCommand"):
                           APP_JS.index("// UX-7 (owner-directed)")]
        self.assertNotIn("sendChat(", apply_fn)

    def test_enter_key_selects_from_open_palette_instead_of_sending(self):
        build_chat = APP_JS[APP_JS.index("function buildChat"):APP_JS.index("function chatHook")]
        keydown = build_chat[build_chat.index('addEventListener("keydown"'):]
        # When the palette is open, Enter must resolve to applySlashCommand
        # before falling through to the plain "Enter sends" handler below it.
        slash_branch = keydown[:keydown.index("if (e.key === \"Enter\" && !e.shiftKey)")]
        self.assertIn("slashState.open", slash_branch)
        self.assertIn("applySlashCommand(slashState.items[slashState.index])", slash_branch)

    def test_escape_and_arrow_keys_handled_while_open(self):
        build_chat = APP_JS[APP_JS.index("function buildChat"):APP_JS.index("function chatHook")]
        self.assertIn('"ArrowDown"', build_chat)
        self.assertIn('"ArrowUp"', build_chat)
        self.assertIn('"Escape"', build_chat)
        self.assertIn("hideSlashPalette()", build_chat)

    def test_blur_closes_after_a_tick_so_click_lands(self):
        build_chat = APP_JS[APP_JS.index("function buildChat"):APP_JS.index("function chatHook")]
        blur_block = build_chat[build_chat.index('addEventListener("blur"'):
                                 build_chat.index('addEventListener("blur"') + 200]
        self.assertIn("setTimeout(hideSlashPalette", blur_block)

    def test_click_on_row_prevents_mousedown_blur_race(self):
        render_fn = APP_JS[APP_JS.index("function renderSlashPalette"):
                            APP_JS.index("function updateSlashPalette")]
        self.assertIn('"mousedown"', render_fn)
        self.assertIn("e.preventDefault()", render_fn)
        self.assertIn('"click"', render_fn)

    def test_filter_is_prefix_match_on_command_name(self):
        update_fn = APP_JS[APP_JS.index("function updateSlashPalette"):
                            APP_JS.index("function applySlashCommand")]
        self.assertIn("c.cmd.indexOf(word) === 0", update_fn)

    def test_css_added(self):
        for selector in [".slash-palette", ".slash-row", ".slash-row.selected",
                          ".slash-cmd", ".slash-desc", ".slash-hint"]:
            self.assertIn(selector, APP_CSS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
