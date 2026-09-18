#!/usr/bin/env python3
"""
Create a new ReconcileHub reconciliation-module skeleton.

Example:
    python scripts/create_reconciliation_module.py cash_register \
        --name "Сверка кассы" \
        --category "Касса" \
        --author "Финансовый отдел"

The generated module is discovered automatically through MODULE_CLASS.
Implement validate_inputs() and run() before assigning permissions to users.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = ROOT / "modules"


def validate_module_id(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise argparse.ArgumentTypeError(
            "module_id must start with a lowercase letter and contain only "
            "lowercase letters, digits and underscores"
        )
    return value


def class_name(module_id: str) -> str:
    return "".join(part.capitalize() for part in module_id.split("_")) + "Module"


def build_engine(module_id: str, name: str, category: str, author: str) -> str:
    cls = class_name(module_id)
    return f'''"""
{name} reconciliation module.
"""
from typing import Any, Dict, Optional

from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ReconResult,
    ValidationResult,
)


class {cls}(BaseReconciliationModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="{module_id}",
            name={name!r},
            version="0.1.0",
            description="TODO: опишите назначение сверки.",
            category={category!r},
            icon="Layers",
            author={author!r},
            status="draft",
            workspace=None,
            required_permissions=["{module_id}.view", "{module_id}.run"],
            required_files=[],
        )

    def validate_inputs(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ValidationResult:
        return ValidationResult(
            is_valid=False,
            errors=["TODO: реализуйте validate_inputs() перед использованием модуля."],
        )

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        raise NotImplementedError("TODO: implement reconciliation logic")

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {{"module": "{module_id}", "run_id": run_id, "metrics": {{}}}}

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        return b""


# ReconcileHub discovers this entrypoint automatically.
MODULE_CLASS = {cls}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a ReconcileHub reconciliation module skeleton")
    parser.add_argument("module_id", type=validate_module_id)
    parser.add_argument("--name", required=True, help="Human-readable reconciliation name")
    parser.add_argument("--category", default="Прочее")
    parser.add_argument("--author", default="Финансовый отдел")
    args = parser.parse_args()

    target = MODULES_DIR / args.module_id
    if target.exists():
        parser.error(f"{target.relative_to(ROOT)} already exists")

    target.mkdir(parents=True)
    (target / "__init__.py").write_text("", encoding="utf-8")
    (target / "engine.py").write_text(
        build_engine(args.module_id, args.name, args.category, args.author),
        encoding="utf-8",
    )

    print(f"Created modules/{args.module_id}/engine.py")
    print("Next steps:")
    print("  1. Implement validate_inputs() and run().")
    print("  2. Define required_files and module-specific permissions in the manifest.")
    print("  3. Add the new permissions to the intended roles in utils/permissions.py.")
    print("  4. If a specialized UI is needed, add its workspace key to src/modules/workspaceRegistry.ts.")
    print("No edit to modules/registry.py is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
