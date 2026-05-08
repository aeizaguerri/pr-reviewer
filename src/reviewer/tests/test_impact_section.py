"""D.3 — Unit tests for _build_impact_section() in src/reviewer/prompts.py."""


from src.knowledge.models import ImpactResult, ImpactWarning
from src.reviewer.prompts import _build_impact_section


def _make_warning(
    *,
    changed_file: str = "path/to/file.py",
    changed_entity: str = "MyContract",
    affected_service: str = "my-svc",
    affected_repository: str = "my-repo",
    relationship_type: str = "CONSUMES",
    severity: str = "medium",
    description: str = "`my-svc` (in `my-repo`) consumes `MyContract`.",
) -> ImpactWarning:
    return ImpactWarning(
        changed_file=changed_file,
        changed_entity=changed_entity,
        affected_service=affected_service,
        affected_repository=affected_repository,
        relationship_type=relationship_type,
        severity=severity,
        description=description,
    )


class TestBuildImpactSection:
    def test_empty_impact_result_returns_empty_string(self, empty_impact_result):
        result = _build_impact_section(empty_impact_result)
        assert result == ""

    def test_impact_result_with_no_warnings_returns_empty_string(self):
        result = _build_impact_section(ImpactResult(warnings=[]))
        assert result == ""

    def test_single_warning_formats_correctly(self):
        warning = _make_warning(
            changed_file="src/contracts/order_created.py",
            changed_entity="OrderCreatedEvent",
            affected_service="payment-worker",
            affected_repository="payment-service",
            severity="high",
            description="`payment-worker` (in `payment-service`) consumes `OrderCreatedEvent`.",
        )
        result = _build_impact_section(ImpactResult(warnings=[warning]))

        assert "## Cross-Repository Impact Analysis" in result
        assert "payment-worker" in result
        assert "payment-service" in result
        assert "OrderCreatedEvent" in result
        assert "HIGH" in result  # severity badge is uppercased
        assert "src/contracts/order_created.py" in result

    def test_multiple_warnings_all_appear_in_output(self):
        warnings = [
            _make_warning(
                affected_service="billing-svc",
                affected_repository="billing-repo",
                changed_entity="PaymentContract",
                severity="high",
            ),
            _make_warning(
                affected_service="notification-svc",
                affected_repository="notification-repo",
                changed_entity="PaymentContract",
                severity="low",
            ),
        ]
        result = _build_impact_section(ImpactResult(warnings=warnings))

        assert "billing-svc" in result
        assert "billing-repo" in result
        assert "notification-svc" in result
        assert "notification-repo" in result
        assert "HIGH" in result
        assert "LOW" in result

    def test_section_header_is_present(self, sample_impact_result):
        result = _build_impact_section(sample_impact_result)
        assert result.startswith("## Cross-Repository Impact Analysis")

    def test_closing_note_is_present(self, sample_impact_result):
        result = _build_impact_section(sample_impact_result)
        assert "Please consider these downstream impacts in your review." in result

    def test_severity_medium_appears_uppercased(self):
        warning = _make_warning(severity="medium")
        result = _build_impact_section(ImpactResult(warnings=[warning]))
        assert "MEDIUM" in result

    def test_severity_high_appears_uppercased(self):
        warning = _make_warning(severity="high")
        result = _build_impact_section(ImpactResult(warnings=[warning]))
        assert "HIGH" in result

    def test_severity_low_appears_uppercased(self):
        warning = _make_warning(severity="low")
        result = _build_impact_section(ImpactResult(warnings=[warning]))
        assert "LOW" in result

    def test_description_is_included(self):
        warning = _make_warning(
            description="This is a specific description for this test."
        )
        result = _build_impact_section(ImpactResult(warnings=[warning]))
        assert "This is a specific description for this test." in result

    def test_output_is_valid_markdown(self, sample_impact_result):
        """Spot-check: output contains markdown bold markers and backtick formatting."""
        result = _build_impact_section(sample_impact_result)
        assert "**" in result
        assert "`" in result

    def test_prompt_injection_format_prepends_before_diff(self, sample_impact_result):
        """Verify that the section can be prepended cleanly to a prompt string."""
        prompt = "PR title: My PR\n\nDiff content here."
        section = _build_impact_section(sample_impact_result)
        enriched_prompt = section + "\n\n" + prompt
        assert enriched_prompt.startswith("## Cross-Repository Impact Analysis")
        assert "PR title: My PR" in enriched_prompt
        # Impact section must come BEFORE the diff
        impact_pos = enriched_prompt.index("## Cross-Repository Impact Analysis")
        diff_pos = enriched_prompt.index("Diff content here.")
        assert impact_pos < diff_pos
