"""D.4 — Unit tests for src/knowledge/population.py."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml
from pydantic import ValidationError

from src.knowledge.models import (
    ContractDef,
    FieldDef,
    RepoDef,
    SchemaDef,
    ServiceDef,
    TopologyConfig,
)
from src.knowledge.population import load_topology, populate_graph


# ---------------------------------------------------------------------------
# load_topology() tests
# ---------------------------------------------------------------------------


class TestLoadTopology:
    def test_loads_example_topology_yaml(self, topology_yaml_path: Path):
        """The examples/topology.yaml file must load without errors."""
        topology = load_topology(topology_yaml_path)
        assert isinstance(topology, TopologyConfig)
        assert len(topology.repositories) == 3

    def test_example_topology_has_expected_repos(self, topology_yaml_path: Path):
        topology = load_topology(topology_yaml_path)
        repo_names = [r.name for r in topology.repositories]
        assert "order-service" in repo_names
        assert "payment-service" in repo_names
        assert "notification-service" in repo_names

    def test_example_topology_has_contracts(self, topology_yaml_path: Path):
        topology = load_topology(topology_yaml_path)
        # order-service produces OrderCreatedEvent and OrderCancelledEvent
        order_repo = next(r for r in topology.repositories if r.name == "order-service")
        order_api = order_repo.services[0]
        contract_names = [c.name for c in order_api.produces]
        assert "OrderCreatedEvent" in contract_names
        assert "OrderCancelledEvent" in contract_names

    def test_example_topology_has_schema_fields(self, topology_yaml_path: Path):
        topology = load_topology(topology_yaml_path)
        order_repo = next(r for r in topology.repositories if r.name == "order-service")
        order_api = order_repo.services[0]
        order_created = next(c for c in order_api.produces if c.name == "OrderCreatedEvent")
        payload = order_created.schemas[0]
        assert payload.name == "OrderCreatedPayload"
        field_names = [f.name for f in payload.fields]
        assert "order_id" in field_names
        assert "customer_email" in field_names

    def test_example_topology_consumes_relationships(self, topology_yaml_path: Path):
        topology = load_topology(topology_yaml_path)
        payment_repo = next(r for r in topology.repositories if r.name == "payment-service")
        payment_worker = payment_repo.services[0]
        assert "OrderCreatedEvent" in payment_worker.consumes

    def test_raises_file_not_found_for_missing_path(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_topology(tmp_path / "nonexistent.yaml")

    def test_raises_validation_error_for_missing_required_field(self, tmp_path: Path):
        """A YAML missing required 'name' for a repo must raise ValidationError."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "version: '1'\n"
            "repositories:\n"
            "  - description: 'Missing name'\n"
            "    services: []\n"
        )
        with pytest.raises(ValidationError):
            load_topology(bad_yaml)

    def test_raises_validation_error_for_missing_service_name(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad_svc.yaml"
        bad_yaml.write_text(
            "version: '1'\n"
            "repositories:\n"
            "  - name: my-repo\n"
            "    services:\n"
            "      - description: 'Missing name'\n"
        )
        with pytest.raises(ValidationError):
            load_topology(bad_yaml)

    def test_empty_yaml_file_returns_default_topology(self, tmp_path: Path):
        """An empty YAML file must produce a default TopologyConfig with no repos."""
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        topology = load_topology(empty)
        assert isinstance(topology, TopologyConfig)
        assert topology.repositories == []

    def test_accepts_path_as_string(self, topology_yaml_path: Path):
        topology = load_topology(str(topology_yaml_path))
        assert isinstance(topology, TopologyConfig)


# ---------------------------------------------------------------------------
# populate_graph() tests
# ---------------------------------------------------------------------------


def _make_minimal_topology() -> TopologyConfig:
    """A minimal valid topology: 1 repo → 1 service → 1 contract."""
    return TopologyConfig(
        repositories=[
            RepoDef(
                name="my-repo",
                services=[
                    ServiceDef(
                        name="my-svc",
                        produces=[
                            ContractDef(
                                name="MyContract",
                                file_path="src/contracts/my_contract.py",
                                type="event",
                            )
                        ],
                        consumes=[],
                    )
                ],
            )
        ]
    )


def _make_topology_with_consumer() -> TopologyConfig:
    """Two services: producer + consumer, linked via MyContract."""
    return TopologyConfig(
        repositories=[
            RepoDef(
                name="producer-repo",
                services=[
                    ServiceDef(
                        name="producer-svc",
                        produces=[ContractDef(name="SharedContract", type="event")],
                        consumes=[],
                    )
                ],
            ),
            RepoDef(
                name="consumer-repo",
                services=[
                    ServiceDef(
                        name="consumer-svc",
                        produces=[],
                        consumes=["SharedContract"],
                    )
                ],
            ),
        ]
    )


def _make_topology_with_schema_fields() -> TopologyConfig:
    """Topology with a contract that has a schema with fields."""
    return TopologyConfig(
        repositories=[
            RepoDef(
                name="field-repo",
                services=[
                    ServiceDef(
                        name="field-svc",
                        produces=[
                            ContractDef(
                                name="FieldContract",
                                schemas=[
                                    SchemaDef(
                                        name="FieldSchema",
                                        fields=[
                                            FieldDef(name="id", type="str"),
                                            FieldDef(name="value", type="float"),
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ]
    )


class TestPopulateGraph:
    def _make_mock_driver(self):
        """Returns a mock driver that captures all tx.run() calls."""
        mock_tx = MagicMock()
        mock_tx.run = MagicMock()

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        # execute_write captures and calls the lambda with mock_tx
        mock_session.execute_write = MagicMock(
            side_effect=lambda fn: fn(mock_tx)
        )

        mock_driver = MagicMock()
        mock_driver.session = MagicMock(return_value=mock_session)

        return mock_driver, mock_tx

    def test_populate_graph_calls_execute_write(self):
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        populate_graph(driver, topology)
        driver.session().__exit__.assert_called()

    def test_populate_graph_merges_repository_node(self):
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        populate_graph(driver, topology)

        # Find the MERGE call for Repository node
        calls_args = [str(c) for c in mock_tx.run.call_args_list]
        repo_calls = [c for c in calls_args if "Repository" in c and "my-repo" in c]
        assert len(repo_calls) >= 1, "Expected at least one MERGE for Repository node"

    def test_populate_graph_merges_service_node(self):
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        populate_graph(driver, topology)

        calls_args = [str(c) for c in mock_tx.run.call_args_list]
        svc_calls = [c for c in calls_args if "Service" in c and "my-svc" in c]
        assert len(svc_calls) >= 1, "Expected at least one MERGE for Service node"

    def test_populate_graph_merges_contract_node(self):
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        populate_graph(driver, topology)

        calls_args = [str(c) for c in mock_tx.run.call_args_list]
        contract_calls = [c for c in calls_args if "Contract" in c and "MyContract" in c]
        assert len(contract_calls) >= 1, "Expected at least one MERGE for Contract node"

    def test_populate_graph_total_run_calls_for_minimal_topology(self):
        """Minimal topology: 1 repo + 1 svc + 1 contract = 3 MERGE operations."""
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        populate_graph(driver, topology)
        # Expect: MERGE Repository, MERGE Service (+ OWNS rel), MERGE Contract (+ PRODUCES rel)
        # That's 3 tx.run() calls (each MERGE also sets the relationship in same call)
        assert mock_tx.run.call_count == 3

    def test_populate_graph_consumes_relationship_is_merged(self):
        driver, mock_tx = self._make_mock_driver()
        topology = _make_topology_with_consumer()
        populate_graph(driver, topology)

        calls_args = [str(c) for c in mock_tx.run.call_args_list]
        consumes_calls = [c for c in calls_args if "CONSUMES" in c]
        assert len(consumes_calls) >= 1, "Expected at least one MERGE for CONSUMES relationship"

    def test_populate_graph_field_nodes_are_merged(self):
        driver, mock_tx = self._make_mock_driver()
        topology = _make_topology_with_schema_fields()
        populate_graph(driver, topology)

        calls_args = [str(c) for c in mock_tx.run.call_args_list]
        field_calls = [c for c in calls_args if "Field" in c]
        # FieldSchema has 2 fields → 2 MERGE Field calls
        assert len(field_calls) >= 2, "Expected MERGE calls for Field nodes"

    def test_populate_graph_returns_stats_dict(self):
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        stats = populate_graph(driver, topology)
        assert "nodes_created" in stats
        assert "relationships_created" in stats
        assert isinstance(stats["nodes_created"], int)
        assert isinstance(stats["relationships_created"], int)

    def test_populate_graph_nodes_created_count_matches_topology(self):
        """Minimal topology: repo(1) + svc(1) + contract(1) = 3 nodes."""
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        stats = populate_graph(driver, topology)
        assert stats["nodes_created"] == 3

    def test_populate_graph_relationships_created_count_minimal(self):
        """Minimal topology: OWNS(1) + PRODUCES(1) = 2 relationships."""
        driver, mock_tx = self._make_mock_driver()
        topology = _make_minimal_topology()
        stats = populate_graph(driver, topology)
        assert stats["relationships_created"] == 2

    def test_populate_graph_schema_fields_run_calls(self):
        """Topology with 1 schema and 2 fields: repo + svc + contract + schema + 2 fields = 6 nodes."""
        driver, mock_tx = self._make_mock_driver()
        topology = _make_topology_with_schema_fields()
        stats = populate_graph(driver, topology)
        # repo(1) + svc(1) + contract(1) + schema(1) + field(2) = 6 nodes
        assert stats["nodes_created"] == 6
