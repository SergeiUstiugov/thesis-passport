#!/usr/bin/env python3
"""Мутационная проверка самого теста.

Каждая мутация портит одну строку в assign_status. Хороший тест должен
провалиться на каждой из них («мутант убит»). Если мутант выжил, тест
не замечает такой ошибки — это повод его усилить.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / "check_rules.py").read_text(encoding="utf-8")

MUTANTS = [
    ("интерпретация не проверяется",
     '    if x["interpretation"]:\n        return "analyst_required"\n', ""),
    ("нет источника не проверяется",
     '    if not x["sources"]:\n        return "insufficient_data"\n', ""),
    ("строгое сравнение заменено нестрогим",
     'if x["new"] < x["old"]:', 'if x["new"] <= x["old"]:'),
    ("противоречие опор проверяется после сопоставимости",
     '    if x["conflicting"]:\n        return "clarify"\n    if not (x["same_scope"] and x["same_definition"]):\n        return "not_comparable"\n',
     '    if not (x["same_scope"] and x["same_definition"]):\n        return "not_comparable"\n    if x["conflicting"]:\n        return "clarify"\n'),
    ("проверяется только периметр",
     'if not (x["same_scope"] and x["same_definition"]):', 'if not x["same_scope"]:'),
    ("нет значения даёт противоречие",
     '    if x["old"] is None or x["new"] is None:\n        return "insufficient_data"\n',
     '    if x["old"] is None or x["new"] is None:\n        return "contradicted"\n'),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    survived = 0
    for name, old, new in MUTANTS:
        impl_start = SOURCE.index("def assign_status")
        impl_end = SOURCE.index("# --- Эталон")
        impl = SOURCE[impl_start:impl_end]
        if old not in impl:
            print(f"ОШИБКА МУТАЦИИ: фрагмент не найден — {name}")
            return 2
        mutated = SOURCE[:impl_start] + impl.replace(old, new, 1) + SOURCE[impl_end:]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "check_rules.py").write_text(mutated, encoding="utf-8")
            (tmp / "cases.json").write_bytes((HERE / "cases.json").read_bytes())
            rc = subprocess.run([sys.executable, str(tmp / "check_rules.py")],
                                capture_output=True).returncode
        killed = rc != 0
        survived += not killed
        print(f"{'убит   ' if killed else 'ВЫЖИЛ  '} {name}")
    print(f"Мутантов: {len(MUTANTS)}, выжило: {survived}")
    return 0 if survived == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
