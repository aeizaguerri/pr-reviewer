"""Unit tests: L2 — Anti-injection defense paragraph in REVIEWER_INSTRUCTIONS."""

from src.reviewer.prompts import REVIEWER_INSTRUCTIONS


class TestAntiInjectionParagraph:
    """SC-L2-1: Verify the defense paragraph is present in REVIEWER_INSTRUCTIONS."""

    def test_untrusted_keyword_present(self):
        """Instructions must mention 'untrusted' in relation to diff/input content."""
        assert "untrusted" in REVIEWER_INSTRUCTIONS.lower()

    def test_diff_content_tag_referenced(self):
        """Instructions must reference the <diff_content> XML delimiter."""
        assert "<diff_content>" in REVIEWER_INSTRUCTIONS

    def test_pr_title_tag_referenced(self):
        """Instructions must reference the <pr_title> XML delimiter."""
        assert "<pr_title>" in REVIEWER_INSTRUCTIONS

    def test_ignore_embedded_instructions(self):
        """Instructions must tell the LLM to ignore embedded directives."""
        lower = REVIEWER_INSTRUCTIONS.lower()
        # Any of these phrases indicate the anti-injection intent
        assert any(
            phrase in lower
            for phrase in [
                "ignore",
                "never follow",
                "do not follow",
            ]
        ), "Expected an instruction to ignore embedded directives"

    def test_security_section_heading(self):
        """A 'Security' or 'Untrusted' section heading must be present."""
        assert (
            "Security" in REVIEWER_INSTRUCTIONS or "CRITICAL" in REVIEWER_INSTRUCTIONS
        )

    def test_instructions_is_non_empty_string(self):
        """Sanity: the constant must be a non-empty string."""
        assert isinstance(REVIEWER_INSTRUCTIONS, str)
        assert len(REVIEWER_INSTRUCTIONS) > 100


class TestTagNameCrossLayerConsistency:
    """S1: Tag names in REVIEWER_INSTRUCTIONS must match those used in _make_prompt()."""

    def test_diff_content_tag_in_both_instructions_and_prompt(self):
        """<diff_content> tag referenced in prompts.py must appear in _make_prompt() output."""
        from src.reviewer.agent import _make_prompt

        prompt = _make_prompt("title", "diff")
        assert "<diff_content>" in REVIEWER_INSTRUCTIONS
        assert "<diff_content>" in prompt

    def test_pr_title_tag_in_both_instructions_and_prompt(self):
        """<pr_title> tag referenced in prompts.py must appear in _make_prompt() output."""
        from src.reviewer.agent import _make_prompt

        prompt = _make_prompt("title", "diff")
        assert "<pr_title>" in REVIEWER_INSTRUCTIONS
        assert "<pr_title>" in prompt
