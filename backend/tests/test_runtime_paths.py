from __future__ import annotations

import importlib
from pathlib import Path


def _clear_runtime_path_env(monkeypatch) -> None:
    for key in (
        "AELIN_BACKEND_ASSET_ROOT",
        "AELIN_APP_DATA_DIR",
        "AELIN_OUTPUT_ROOT",
        "AELIN_MEMORY_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_runtime_paths_default_to_repo_relative_roots(monkeypatch):
    import app.runtime_paths as runtime_paths

    _clear_runtime_path_env(monkeypatch)
    runtime_paths = importlib.reload(runtime_paths)

    assert runtime_paths.backend_root().name == "backend"
    assert runtime_paths.repo_root() == runtime_paths.backend_root().parent
    assert runtime_paths.app_data_root() == runtime_paths.repo_root() / "data"
    assert runtime_paths.output_root() == runtime_paths.repo_root() / "output"
    assert runtime_paths.memory_root() == runtime_paths.repo_root() / "data" / "aelin_memory"
    assert runtime_paths.deepagents_skills_root() == runtime_paths.backend_root() / "deepagents_skills"


def test_delivery_paths_use_output_root_override(monkeypatch, tmp_path: Path):
    import app.runtime_paths as runtime_paths
    import app.services.deepagents.delivery_paths as delivery_paths

    _clear_runtime_path_env(monkeypatch)
    monkeypatch.setenv("AELIN_OUTPUT_ROOT", str(tmp_path / "desktop-output"))
    runtime_paths = importlib.reload(runtime_paths)
    delivery_paths = importlib.reload(delivery_paths)

    paths = delivery_paths.get_delivery_paths(workspace="Demo Workspace", user_id=12, create=False)

    assert paths.root_dir == (runtime_paths.output_root() / "deepagents" / "user-12" / "demo-workspace").resolve()
    assert paths.workspace_dir == (paths.root_dir / "workspace").resolve()
    assert paths.outputs_dir == (paths.root_dir / "outputs").resolve()


def test_backend_factory_uses_backend_asset_root_override(monkeypatch, tmp_path: Path):
    import app.runtime_paths as runtime_paths
    import app.services.deepagents.assembly.backend_factory as backend_factory

    _clear_runtime_path_env(monkeypatch)
    monkeypatch.setenv("AELIN_BACKEND_ASSET_ROOT", str(tmp_path / "backend-runtime"))
    runtime_paths = importlib.reload(runtime_paths)
    backend_factory = importlib.reload(backend_factory)

    assert backend_factory._backend_root() == runtime_paths.backend_asset_root()


def test_resolve_local_artifact_path_uses_output_root_for_relative_paths(monkeypatch, tmp_path: Path):
    import app.runtime_paths as runtime_paths
    import app.services.artifact_files as artifact_files

    _clear_runtime_path_env(monkeypatch)
    output_root = tmp_path / "output-root"
    target_file = output_root / "generated-posters" / "demo.txt"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("artifact", encoding="utf-8")
    monkeypatch.setenv("AELIN_OUTPUT_ROOT", str(output_root))

    runtime_paths = importlib.reload(runtime_paths)
    artifact_files = importlib.reload(artifact_files)

    resolved = artifact_files.resolve_local_artifact_path("generated-posters/demo.txt")

    assert resolved == target_file.resolve()


def test_runtime_readiness_reports_packaged_safe_roots(monkeypatch, tmp_path: Path):
    import app.runtime_paths as runtime_paths
    import app.services.runtime_readiness as runtime_readiness

    _clear_runtime_path_env(monkeypatch)
    monkeypatch.setenv("AELIN_APP_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("AELIN_OUTPUT_ROOT", str(tmp_path / "output"))
    monkeypatch.setenv("AELIN_MEMORY_ROOT", str(tmp_path / "memory"))
    runtime_paths = importlib.reload(runtime_paths)
    runtime_readiness = importlib.reload(runtime_readiness)

    report = runtime_readiness.runtime_readiness_report()

    assert report["ok"] is True
    assert report["paths"]["app_data_root"]["path"] == str(runtime_paths.app_data_root())
    assert report["paths"]["output_root"]["path"] == str(runtime_paths.output_root())
    assert report["paths"]["memory_root"]["path"] == str(runtime_paths.memory_root())
