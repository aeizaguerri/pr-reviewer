"""Unit tests: prompt constants and anti-injection prompt behavior."""

import json
import re
from pathlib import Path

from src.knowledge.models import ImpactWarning
from src.reviewer.models import BugReport
from src.reviewer.prompts import REVIEWER_INSTRUCTIONS


def _read_prompt(name: str) -> str:
    return Path(f"prompts/{name}.txt").read_text(encoding="utf-8")


def _extract_json_block(prompt: str, label: str) -> dict:
    pattern = rf"{re.escape(label)}:\n```json\n(.*?)\n```"
    match = re.search(pattern, prompt, re.DOTALL)
    assert match, f"Missing JSON block for {label}"
    return json.loads(match.group(1))


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
        assert "Security" in REVIEWER_INSTRUCTIONS or "CRITICAL" in REVIEWER_INSTRUCTIONS

    def test_instructions_is_non_empty_string(self):
        """Sanity: the constant must be a non-empty string."""
        assert isinstance(REVIEWER_INSTRUCTIONS, str)
        assert len(REVIEWER_INSTRUCTIONS) > 100


class TestMultiAgentPromptConstants:
    def test_specialist_constants_load_through_prompt_registry(self, monkeypatch):
        import src.reviewer.prompts as prompts

        for attr in (
            "BUG_REVIEWER_INSTRUCTIONS",
            "SECURITY_REVIEWER_INSTRUCTIONS",
            "CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS",
        ):
            prompts.__dict__.pop(attr, None)

        requested: list[str] = []

        def fake_get_prompt(name: str) -> str:
            requested.append(name)
            return f"loaded:{name}"

        monkeypatch.setattr(prompts, "get_prompt", fake_get_prompt)

        assert prompts.BUG_REVIEWER_INSTRUCTIONS == "loaded:bug_reviewer_instructions"
        assert prompts.SECURITY_REVIEWER_INSTRUCTIONS == "loaded:security_reviewer_instructions"
        assert (
            prompts.CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS
            == "loaded:cross_repo_impact_reviewer_instructions"
        )
        assert requested == [
            "bug_reviewer_instructions",
            "security_reviewer_instructions",
            "cross_repo_impact_reviewer_instructions",
        ]

    def test_reviewer_instructions_keeps_compat_loader(self, monkeypatch):
        import src.reviewer.prompts as prompts

        prompts.__dict__.pop("REVIEWER_INSTRUCTIONS", None)
        monkeypatch.setattr(prompts, "get_reviewer_prompt", lambda: "compat reviewer")

        assert prompts.REVIEWER_INSTRUCTIONS == "compat reviewer"

    def test_local_security_prompt_excludes_general_correctness_bugs(self):
        from pathlib import Path

        prompt = Path("prompts/security_reviewer_instructions.txt").read_text(
            encoding="utf-8"
        )
        lower = prompt.lower()

        assert "exploitable" in lower
        assert "realistic" in lower
        assert "general correctness bugs" in lower
        assert "validation issues without attacker impact" in lower
        assert "attacker" in lower


class TestSpecialistPromptContracts:
    def test_bug_prompt_contract_rules_and_examples(self):
        prompt = _read_prompt("bug_reviewer_instructions")

        assert "Output contract:" in prompt
        for expected in (
            "Return ONLY valid JSON.",
            "Do NOT include markdown fences.",
            "Do NOT include prose before or after JSON.",
            "Do NOT rename fields.",
            "Do NOT omit required fields.",
            "Use an empty array when there are no findings.",
            "Do NOT use `warning` here. `warning` is reserved for later aggregation.",
        ):
            assert expected in prompt

        assert '`{"Bugs":[]}`' in prompt
        assert '`{"bugs":[{"type":"bug"}]}`' in prompt

        exact_shape = _extract_json_block(prompt, "Exact JSON shape")
        assert set(exact_shape) == {"bugs"}
        BugReport.model_validate(exact_shape["bugs"][0])

        valid_example = _extract_json_block(prompt, "Valid finding output example")
        empty_example = _extract_json_block(prompt, "Empty-output example")

        assert empty_example == {"bugs": []}
        assert len(valid_example["bugs"]) == 1
        bug = BugReport.model_validate(valid_example["bugs"][0])
        assert bug.category == "bug"
        assert bug.severity in {"critical", "major", "minor"}
        assert bug.severity != "warning"

    def test_security_prompt_contract_rules_and_examples(self):
        prompt = _read_prompt("security_reviewer_instructions")

        assert "Output contract:" in prompt
        for expected in (
            "Return ONLY valid JSON.",
            "Do NOT include markdown fences.",
            "Do NOT include prose before or after JSON.",
            "Do NOT rename fields.",
            "Do NOT omit required fields.",
            "Use an empty array when there are no findings.",
            "Do NOT use `warning` here. `warning` is reserved for later aggregation.",
            "Set `category` to `security` for every finding.",
        ):
            assert expected in prompt

        assert '`{"Bugs":[]}`' in prompt
        assert '`{"bugs":[{"type":"security"}]}`' in prompt

        exact_shape = _extract_json_block(prompt, "Exact JSON shape")
        assert set(exact_shape) == {"bugs"}
        BugReport.model_validate(exact_shape["bugs"][0])

        valid_example = _extract_json_block(prompt, "Valid finding output example")
        empty_example = _extract_json_block(prompt, "Empty-output example")

        assert empty_example == {"bugs": []}
        assert len(valid_example["bugs"]) == 1
        bug = BugReport.model_validate(valid_example["bugs"][0])
        assert bug.category == "security"
        assert bug.severity in {"critical", "major", "minor"}
        assert bug.severity != "warning"

    def test_cross_repo_prompt_contract_rules_and_examples(self):
        prompt = _read_prompt("cross_repo_impact_reviewer_instructions")

        assert "Output contract:" in prompt
        for expected in (
            "Return ONLY valid JSON.",
            "Do NOT include markdown fences.",
            "Do NOT include prose before or after JSON.",
            "Do NOT rename fields.",
            "Do NOT omit required fields.",
            "Use an empty array when there are no findings.",
        ):
            assert expected in prompt

        assert '`{"ImpactWarnings":[]}`' in prompt
        assert '`{"impact_warnings":[{"type":"impact"}]}`' in prompt

        exact_shape = _extract_json_block(prompt, "Exact JSON shape")
        assert set(exact_shape) == {"impact_warnings"}
        ImpactWarning.model_validate(exact_shape["impact_warnings"][0])

        valid_example = _extract_json_block(prompt, "Valid finding output example")
        empty_example = _extract_json_block(prompt, "Empty-output example")

        assert empty_example == {"impact_warnings": []}
        assert len(valid_example["impact_warnings"]) == 1
        warning = ImpactWarning.model_validate(valid_example["impact_warnings"][0])
        assert warning.severity == "high"


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
