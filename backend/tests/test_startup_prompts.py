"""Backend startup tests for Opik prompt warmup."""

from fastapi.testclient import TestClient


def test_lifespan_configures_opik_before_warming_prompt_cache(monkeypatch):
    import backend.main as main_module

    calls: list[str] = []

    monkeypatch.setattr(main_module, "configure_opik", lambda: calls.append("configure_opik"))
    monkeypatch.setattr(
        main_module,
        "warm_prompt_cache",
        lambda names: calls.append(f"warm:{','.join(names)}"),
    )
    monkeypatch.setattr(main_module.Config, "validate", lambda: None)

    with TestClient(main_module.app):
        pass

    assert calls == [
        "configure_opik",
        "warm:bug_reviewer_instructions,security_reviewer_instructions,"
        "cross_repo_impact_reviewer_instructions,pr_review_prompt",
    ]


def test_lifespan_calls_config_validate_exactly_once(monkeypatch):
    import backend.main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module.Config, "validate", lambda: calls.append("validate"))

    with TestClient(main_module.app):
        pass

    assert calls == ["validate"]
