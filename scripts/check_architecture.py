"""Lightweight architecture guardrails for backend and frontend imports."""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_FEATURES = ROOT / "backend" / "app" / "features"
FRONTEND_RESULTS = ROOT / "frontend" / "results"

FEATURE_IMPORT_PATTERN = re.compile(
    r"""(?:import|export)\s+(?:[^'"]+\s+from\s+)?['"](?P<specifier>[^'"]+)['"]|import\(\s*['"](?P<dynamic>[^'"]+)['"]\s*\)"""
)
FRONTEND_STATE_ASSIGNMENT_PATTERN = re.compile(
    r"""\bstate(?:\.[A-Za-z_$][\w$]*)+\s*(?:=[^=>=]|\+=|-=|\*=|/=|%=|\+\+|--)"""
)

BACKEND_ALLOWED_CROSS_FEATURE_IMPORTS = {
    # Auth owns session flow but logout also clears in-memory uploaded results.
    ("auth/routes.py", "app.features.results.store"),
    # Export builds reports from analysis contracts and result-store snapshots.
    ("export/report_export_service/content.py", "app.features.analysis.topic_analysis_services.contracts"),
    ("export/report_export_service/content.py", "app.features.results.store"),
    # Result storage persists analysis output contracts and prepares analysis-ready datasets.
    ("results/models.py", "app.features.analysis.topic_analysis_services.contracts"),
    ("results/snapshot.py", "app.features.analysis.topic_analysis_services.contracts"),
    ("results/store.py", "app.features.analysis.topic_analysis_services.contracts"),
    ("results/store.py", "app.features.ingestion.cleaning_services"),
}

FRONTEND_SHARED_ALLOWED_TARGETS = {FRONTEND_RESULTS / "shared.js"}
FRONTEND_RESULTS_ALLOWED_ROOT_JS = {
    "analysis.js",
    "charts.js",
    "columnRoles.js",
    "dataExport.js",
    "filters.js",
    "modals.js",
    "resultsEventBindings.js",
    "shared.js",
}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str

    def format(self) -> str:
        relative_path = self.path.relative_to(ROOT).as_posix()
        return f"{relative_path}:{self.line}: {self.message}"


def main() -> int:
    violations = [
        *check_backend_feature_imports(),
        *check_frontend_results_root_files(),
        *check_frontend_shared_imports(),
        *check_frontend_state_mutations(),
    ]
    if violations:
        print("Architecture guardrail violations found:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation.format()}", file=sys.stderr)
        return 1
    print("architecture ok")
    return 0


def check_backend_feature_imports() -> list[Violation]:
    violations: list[Violation] = []
    for path in BACKEND_FEATURES.rglob("*.py"):
        source_feature = get_backend_source_feature(path)
        if not source_feature or source_feature == "common":
            continue
        source_rel = path.relative_to(BACKEND_FEATURES).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported_modules = backend_imported_modules(node)
            for module in imported_modules:
                imported_feature = get_imported_backend_feature(module)
                if not imported_feature or imported_feature in {source_feature, "common"}:
                    continue
                if is_allowed_backend_cross_import(source_rel, module):
                    continue
                violations.append(
                    Violation(
                        path=path,
                        line=getattr(node, "lineno", 1),
                        message=(
                            f"{source_feature!r} feature imports sideways from {imported_feature!r} via {module!r}. "
                            "Move the contract to app.features.common or add a documented exception."
                        ),
                    )
                )
    return violations


def backend_imported_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.ImportFrom) and node.module:
        if node.module == "app.features":
            return [f"{node.module}.{alias.name}" for alias in node.names]
        return [node.module]
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return []


def get_backend_source_feature(path: Path) -> str | None:
    relative_parts = path.relative_to(BACKEND_FEATURES).parts
    if len(relative_parts) < 2:
        return None
    return relative_parts[0]


def get_imported_backend_feature(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 3 or parts[:2] != ["app", "features"]:
        return None
    return parts[2]


def is_allowed_backend_cross_import(source_rel: str, module: str) -> bool:
    return any(
        source_rel == allowed_source and (module == allowed_module or module.startswith(f"{allowed_module}."))
        for allowed_source, allowed_module in BACKEND_ALLOWED_CROSS_FEATURE_IMPORTS
    )


def check_frontend_shared_imports() -> list[Violation]:
    violations: list[Violation] = []
    shared_paths = [FRONTEND_RESULTS / "shared.js", *sorted((FRONTEND_RESULTS / "shared").glob("*.js"))]
    for path in shared_paths:
        text = path.read_text(encoding="utf-8")
        for match in FEATURE_IMPORT_PATTERN.finditer(text):
            specifier = match.group("specifier") or match.group("dynamic") or ""
            if not specifier.startswith("."):
                continue
            target = resolve_frontend_import(path, specifier)
            if not target or is_allowed_frontend_shared_target(target):
                continue
            violations.append(
                Violation(
                    path=path,
                    line=text.count("\n", 0, match.start()) + 1,
                    message=(
                        f"shared module imports non-shared frontend code via {specifier!r}. "
                        "Shared may depend on constants/shared only; move feature-specific logic out of shared."
                    ),
                )
            )
    return violations


def check_frontend_results_root_files() -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(FRONTEND_RESULTS.glob("*.js")):
        if path.name in FRONTEND_RESULTS_ALLOWED_ROOT_JS or path.name.endswith(".test.js"):
            continue
        violations.append(
            Violation(
                path=path,
                line=1,
                message=(
                    "results root JS files must be public facades or tests. "
                    "Move implementation into analysis/, charts/, data/, events/, shared/, or workspace/."
                ),
            )
        )
    return violations


def check_frontend_state_mutations() -> list[Violation]:
    violations: list[Violation] = []
    allowed_paths = {FRONTEND_RESULTS / "shared" / "state.js"}
    for path in sorted(FRONTEND_RESULTS.rglob("*.js")):
        if path in allowed_paths or path.name.endswith(".test.js"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in FRONTEND_STATE_ASSIGNMENT_PATTERN.finditer(text):
            violations.append(
                Violation(
                    path=path,
                    line=text.count("\n", 0, match.start()) + 1,
                    message=(
                        "frontend global state must be mutated through shared/state.js transition helpers. "
                        "Add a named helper there instead of assigning to state directly."
                    ),
                )
            )
    return violations


def resolve_frontend_import(source_path: Path, specifier: str) -> Path | None:
    target = (source_path.parent / specifier).resolve()
    if target.suffix:
        return target
    js_target = target.with_suffix(".js")
    if js_target.exists():
        return js_target
    index_target = target / "index.js"
    if index_target.exists():
        return index_target
    return target


def is_allowed_frontend_shared_target(target: Path) -> bool:
    if target in FRONTEND_SHARED_ALLOWED_TARGETS:
        return True
    try:
        target.relative_to(FRONTEND_RESULTS / "shared")
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
