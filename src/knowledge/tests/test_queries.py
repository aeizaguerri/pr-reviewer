"""D.5 — Unit tests for src/knowledge/queries.py."""

from unittest.mock import MagicMock, patch

from neo4j.exceptions import ServiceUnavailable

from src.knowledge.models import ImpactResult
from src.knowledge.queries import find_consumers_of_paths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_driver(rows_contract: list[dict], rows_schema: list[dict] | None = None):
    """Builds a mock driver whose _run_query() returns the provided rows.

    The first call to _run_query returns rows_contract (contract query),
    the second call returns rows_schema (schema query).
    """
    if rows_schema is None:
        rows_schema = []

    mock_driver = MagicMock()
    return mock_driver


def _make_row(
    changed_file: str = "src/contracts/order_created.py",
    changed_entity: str = "OrderCreatedEvent",
    entity_type: str = "Contract",
    affected_service: str = "payment-worker",
    affected_repository: str = "payment-service",
) -> dict:
    return {
        "changed_file": changed_file,
        "changed_entity": changed_entity,
        "entity_type": entity_type,
        "affected_service": affected_service,
        "affected_repository": affected_repository,
    }


# ---------------------------------------------------------------------------
# find_consumers_of_paths() tests
# ---------------------------------------------------------------------------


class TestFindConsumersOfPaths:
    def test_returns_empty_impact_result_for_empty_paths(self):
        driver = MagicMock()
        result = find_consumers_of_paths(driver, [])
        assert isinstance(result, ImpactResult)
        assert result.warnings == []
        # Should NOT even try to query when paths is empty
        driver.session.assert_not_called()

    def test_returns_impact_result_with_warnings_from_mocked_rows(self):
        driver = MagicMock()
        rows = [_make_row()]

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            # First call (contracts) returns 1 row, second call (schemas) returns empty
            mock_run_query.side_effect = [rows, []]
            result = find_consumers_of_paths(driver, ["src/contracts/order_created.py"])

        assert isinstance(result, ImpactResult)
        assert len(result.warnings) == 1
        w = result.warnings[0]
        assert w.changed_file == "src/contracts/order_created.py"
        assert w.changed_entity == "OrderCreatedEvent"
        assert w.affected_service == "payment-worker"
        assert w.affected_repository == "payment-service"
        assert w.relationship_type == "CONSUMES"

    def test_description_is_populated(self):
        driver = MagicMock()
        rows = [_make_row()]

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [rows, []]
            result = find_consumers_of_paths(driver, ["src/contracts/order_created.py"])

        w = result.warnings[0]
        assert w.description != ""
        assert "payment-worker" in w.description
        assert "payment-service" in w.description

    def test_results_from_both_queries_are_combined(self):
        driver = MagicMock()
        contract_row = _make_row(entity_type="Contract")
        schema_row = _make_row(
            changed_file="src/schemas/payload.py",
            changed_entity="OrderPayload",
            entity_type="Schema",
            affected_service="analytics-svc",
            affected_repository="analytics-repo",
        )

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [[contract_row], [schema_row]]
            result = find_consumers_of_paths(
                driver,
                ["src/contracts/order_created.py", "src/schemas/payload.py"],
            )

        assert len(result.warnings) == 2
        services = {w.affected_service for w in result.warnings}
        assert "payment-worker" in services
        assert "analytics-svc" in services

    def test_results_are_capped_at_max_impact_warnings(self, monkeypatch):
        """Results beyond MAX_IMPACT_WARNINGS must be truncated."""
        import src.core.config as cfg_module
        monkeypatch.setattr(cfg_module.Config, "MAX_IMPACT_WARNINGS", 3)

        driver = MagicMock()
        # 5 rows from contract query
        rows = [_make_row(affected_service=f"svc-{i}") for i in range(5)]

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [rows, []]
            result = find_consumers_of_paths(driver, ["some/path.py"])

        assert len(result.warnings) == 3

    def test_query_time_ms_is_populated(self):
        driver = MagicMock()

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [[], []]
            result = find_consumers_of_paths(driver, ["some/path.py"])

        assert result.query_time_ms >= 0.0

    def test_returns_empty_result_on_service_unavailable(self):
        """Neo4j down (ServiceUnavailable) must return empty ImpactResult, not raise."""
        driver = MagicMock()

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = ServiceUnavailable("Connection refused")
            result = find_consumers_of_paths(driver, ["some/path.py"])

        assert isinstance(result, ImpactResult)
        assert result.warnings == []

    def test_returns_empty_result_on_unexpected_exception(self):
        """Any unexpected exception must be caught and return empty ImpactResult."""
        driver = MagicMock()

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = RuntimeError("Unexpected boom")
            result = find_consumers_of_paths(driver, ["some/path.py"])

        assert isinstance(result, ImpactResult)
        assert result.warnings == []

    def test_severity_defaults_to_medium(self):
        driver = MagicMock()
        rows = [_make_row()]

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [rows, []]
            result = find_consumers_of_paths(driver, ["src/contracts/order_created.py"])

        assert result.warnings[0].severity == "medium"

    def test_missing_repository_in_row_defaults_to_unknown(self):
        """If the graph has no OWNS relationship, repository should default gracefully."""
        driver = MagicMock()
        row = {
            "changed_file": "src/contracts/order_created.py",
            "changed_entity": "OrderCreatedEvent",
            "entity_type": "Contract",
            "affected_service": "orphan-svc",
            "affected_repository": None,  # OPTIONAL MATCH returned null
        }

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [[row], []]
            result = find_consumers_of_paths(driver, ["src/contracts/order_created.py"])

        assert result.warnings[0].affected_repository == "unknown-repository"

    def test_multiple_paths_all_passed_to_query(self):
        """All paths must be forwarded to the Cypher UNWIND query."""
        driver = MagicMock()
        paths = ["a.py", "b.py", "c.py"]

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [[], []]
            find_consumers_of_paths(driver, paths)

        # Both calls should have been made with the full paths list
        for c in mock_run_query.call_args_list:
            params = c.args[2] if len(c.args) > 2 else c.kwargs.get("parameters", {})
            assert params.get("paths") == paths

    def test_no_schema_rows_still_returns_contract_results(self):
        """When schema query returns nothing, contract results still appear."""
        driver = MagicMock()
        rows = [_make_row()]

        with patch("src.knowledge.queries._run_query") as mock_run_query:
            mock_run_query.side_effect = [rows, []]  # schemas query returns empty
            result = find_consumers_of_paths(driver, ["src/contracts/order_created.py"])

        assert len(result.warnings) == 1
