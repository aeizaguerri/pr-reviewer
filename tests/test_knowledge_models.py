"""D.1 — Unit tests for src/knowledge/models.py (Pydantic topology + impact models)."""

import pytest
from pydantic import ValidationError

from src.knowledge.models import (
    ContractDef,
    FieldDef,
    ImpactResult,
    ImpactWarning,
    RepoDef,
    SchemaDef,
    ServiceDef,
    TopologyConfig,
)


# ---------------------------------------------------------------------------
# TopologyConfig (topology models)
# ---------------------------------------------------------------------------


class TestTopologyConfig:
    def test_valid_topology_from_dict(self):
        data = {
            "version": "1",
            "repositories": [
                {
                    "name": "order-service",
                    "description": "Manages orders",
                    "services": [
                        {
                            "name": "order-api",
                            "produces": [
                                {
                                    "name": "OrderCreatedEvent",
                                    "file_path": "src/contracts/order_created.py",
                                    "type": "event",
                                    "schemas": [],
                                }
                            ],
                            "consumes": [],
                        }
                    ],
                }
            ],
        }
        topology = TopologyConfig.model_validate(data)
        assert len(topology.repositories) == 1
        repo = topology.repositories[0]
        assert repo.name == "order-service"
        assert len(repo.services) == 1
        svc = repo.services[0]
        assert svc.name == "order-api"
        assert len(svc.produces) == 1
        assert svc.produces[0].name == "OrderCreatedEvent"
        assert svc.produces[0].file_path == "src/contracts/order_created.py"

    def test_topology_version_defaults_to_one(self):
        topology = TopologyConfig.model_validate({"repositories": []})
        assert topology.version == "1"

    def test_topology_repositories_defaults_to_empty_list(self):
        topology = TopologyConfig.model_validate({})
        assert topology.repositories == []

    def test_topology_nested_schemas_and_fields(self):
        data = {
            "repositories": [
                {
                    "name": "my-repo",
                    "services": [
                        {
                            "name": "my-svc",
                            "produces": [
                                {
                                    "name": "MyContract",
                                    "schemas": [
                                        {
                                            "name": "MySchema",
                                            "fields": [
                                                {"name": "id", "type": "str"},
                                                {"name": "amount", "type": "float"},
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        topology = TopologyConfig.model_validate(data)
        schema = topology.repositories[0].services[0].produces[0].schemas[0]
        assert schema.name == "MySchema"
        assert len(schema.fields) == 2
        assert schema.fields[0].name == "id"
        assert schema.fields[0].type == "str"
        assert schema.fields[1].name == "amount"

    def test_topology_invalid_missing_service_name_raises(self):
        """A service without a name field must fail Pydantic validation."""
        data = {
            "repositories": [
                {
                    "name": "my-repo",
                    "services": [
                        {
                            # 'name' is missing — required field
                            "produces": [],
                        }
                    ],
                }
            ]
        }
        with pytest.raises(ValidationError):
            TopologyConfig.model_validate(data)

    def test_topology_invalid_missing_repo_name_raises(self):
        """A repository without a name field must fail Pydantic validation."""
        data = {
            "repositories": [
                {
                    # 'name' is missing — required field
                    "services": [],
                }
            ]
        }
        with pytest.raises(ValidationError):
            TopologyConfig.model_validate(data)

    def test_topology_invalid_missing_contract_name_raises(self):
        data = {
            "repositories": [
                {
                    "name": "my-repo",
                    "services": [
                        {
                            "name": "my-svc",
                            "produces": [
                                {
                                    # 'name' is missing — required field
                                    "type": "event",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        with pytest.raises(ValidationError):
            TopologyConfig.model_validate(data)


# ---------------------------------------------------------------------------
# RepoDef
# ---------------------------------------------------------------------------


class TestRepoDef:
    def test_repo_requires_name(self):
        with pytest.raises(ValidationError):
            RepoDef.model_validate({})

    def test_repo_services_defaults_to_empty(self):
        repo = RepoDef(name="my-repo")
        assert repo.services == []

    def test_repo_description_defaults_to_empty_string(self):
        repo = RepoDef(name="my-repo")
        assert repo.description == ""


# ---------------------------------------------------------------------------
# ServiceDef
# ---------------------------------------------------------------------------


class TestServiceDef:
    def test_service_requires_name(self):
        with pytest.raises(ValidationError):
            ServiceDef.model_validate({})

    def test_service_produces_defaults_to_empty(self):
        svc = ServiceDef(name="my-svc")
        assert svc.produces == []

    def test_service_consumes_defaults_to_empty(self):
        svc = ServiceDef(name="my-svc")
        assert svc.consumes == []


# ---------------------------------------------------------------------------
# ContractDef
# ---------------------------------------------------------------------------


class TestContractDef:
    def test_contract_requires_name(self):
        with pytest.raises(ValidationError):
            ContractDef.model_validate({})

    def test_contract_type_defaults_to_event(self):
        c = ContractDef(name="MyContract")
        assert c.type == "event"

    def test_contract_file_path_defaults_to_empty(self):
        c = ContractDef(name="MyContract")
        assert c.file_path == ""

    def test_contract_schemas_defaults_to_empty(self):
        c = ContractDef(name="MyContract")
        assert c.schemas == []


# ---------------------------------------------------------------------------
# SchemaDef / FieldDef
# ---------------------------------------------------------------------------


class TestSchemaDef:
    def test_schema_requires_name(self):
        with pytest.raises(ValidationError):
            SchemaDef.model_validate({})

    def test_schema_fields_defaults_to_empty(self):
        s = SchemaDef(name="MySchema")
        assert s.fields == []


class TestFieldDef:
    def test_field_requires_name_and_type(self):
        with pytest.raises(ValidationError):
            FieldDef.model_validate({"name": "id"})  # missing type

        with pytest.raises(ValidationError):
            FieldDef.model_validate({"type": "str"})  # missing name

    def test_field_required_defaults_to_true(self):
        f = FieldDef(name="id", type="str")
        assert f.required is True

    def test_field_required_can_be_false(self):
        f = FieldDef(name="reason", type="str", required=False)
        assert f.required is False


# ---------------------------------------------------------------------------
# ImpactWarning
# ---------------------------------------------------------------------------


class TestImpactWarning:
    def test_impact_warning_requires_all_mandatory_fields(self):
        with pytest.raises(ValidationError):
            # missing changed_file, changed_entity, affected_service,
            # affected_repository, relationship_type, description
            ImpactWarning.model_validate({})

    def test_impact_warning_severity_defaults_to_medium(self):
        w = ImpactWarning(
            changed_file="path/to/file.py",
            changed_entity="MyContract",
            affected_service="my-svc",
            affected_repository="my-repo",
            relationship_type="CONSUMES",
            description="some description",
        )
        assert w.severity == "medium"

    def test_impact_warning_all_fields_set_correctly(self):
        w = ImpactWarning(
            changed_file="path/to/file.py",
            changed_entity="OrderCreatedEvent",
            affected_service="payment-worker",
            affected_repository="payment-service",
            relationship_type="CONSUMES",
            severity="high",
            description="payment-worker consumes OrderCreatedEvent.",
        )
        assert w.changed_file == "path/to/file.py"
        assert w.changed_entity == "OrderCreatedEvent"
        assert w.affected_service == "payment-worker"
        assert w.affected_repository == "payment-service"
        assert w.relationship_type == "CONSUMES"
        assert w.severity == "high"
        assert w.description == "payment-worker consumes OrderCreatedEvent."

    def test_impact_warning_missing_changed_file_raises(self):
        with pytest.raises(ValidationError):
            ImpactWarning.model_validate(
                {
                    "changed_entity": "MyContract",
                    "affected_service": "my-svc",
                    "affected_repository": "my-repo",
                    "relationship_type": "CONSUMES",
                    "description": "desc",
                }
            )

    def test_impact_warning_missing_description_raises(self):
        with pytest.raises(ValidationError):
            ImpactWarning.model_validate(
                {
                    "changed_file": "path/to/file.py",
                    "changed_entity": "MyContract",
                    "affected_service": "my-svc",
                    "affected_repository": "my-repo",
                    "relationship_type": "CONSUMES",
                }
            )


# ---------------------------------------------------------------------------
# ImpactResult
# ---------------------------------------------------------------------------


class TestImpactResult:
    def test_impact_result_warnings_defaults_to_empty_list(self):
        result = ImpactResult()
        assert result.warnings == []

    def test_impact_result_query_time_defaults_to_zero(self):
        result = ImpactResult()
        assert result.query_time_ms == 0.0

    def test_impact_result_with_warnings(self, sample_warning):
        result = ImpactResult(warnings=[sample_warning], query_time_ms=42.5)
        assert len(result.warnings) == 1
        assert result.query_time_ms == 42.5

    def test_impact_result_backward_compatible_empty(self):
        """Deserializing without 'warnings' must not raise."""
        result = ImpactResult.model_validate({})
        assert result.warnings == []
