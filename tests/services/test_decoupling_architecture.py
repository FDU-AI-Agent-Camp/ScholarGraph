"""Architecture tests: workflow nodes must not bypass the service layer."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NODES_PATH = REPO_ROOT / "backend" / "graph" / "nodes.py"

# BE modules that must only be reached via backend.services.* facades.
FORBIDDEN_NODE_IMPORT_PREFIXES = (
    "backend.ingest",
    "backend.agents",
    "backend.graph.store",
)

ALLOWED_NODE_IMPORT_PREFIXES = (
    "backend.graph.state",
    "backend.schemas",
    "backend.services",
    "pathlib",
)


def _import_module_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
    return modules


def test_nodes_py_does_not_import_be_modules_directly() -> None:
    modules = _import_module_names(NODES_PATH)
    violations = [
        module
        for module in modules
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN_NODE_IMPORT_PREFIXES)
    ]
    assert violations == [], f"nodes.py must not import BE modules directly: {violations}"


def test_nodes_py_imports_only_allowed_prefixes() -> None:
    modules = _import_module_names(NODES_PATH)
    for module in modules:
        if module.startswith("backend."):
            assert any(
                module == prefix or module.startswith(f"{prefix}.") for prefix in ALLOWED_NODE_IMPORT_PREFIXES
            ), f"unexpected backend import in nodes.py: {module}"


def test_service_facade_files_exist() -> None:
    expected = [
        "backend/services/ingest_service.py",
        "backend/services/agent_service.py",
        "backend/services/graph_persistence_service.py",
        "backend/services/pipeline_completion_service.py",
        "backend/services/pipeline_status_service.py",
        "backend/services/rag_index_service.py",
        "backend/services/errors.py",
    ]
    for relative in expected:
        assert (REPO_ROOT / relative).is_file(), relative
