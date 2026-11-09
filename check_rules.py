#!/usr/bin/env python3
"""Микротест правил назначения статуса — «Паспорт инвестиционного тезиса».

Проверяет одно утверждение: «новое нормализованное значение показателя меньше
старого». Три уровня проверки:

1. Регрессионные кейсы из cases.json — ожидаемые статусы заданы вручную.
2. Полный перебор всех комбинаций входов: реализация assign_status сверяется
   с независимо записанной таблицей решений DECISION_TABLE.
3. Инварианты на всём переборе (например, интерпретация никогда не получает
   статус confirmed).

Только стандартная библиотека Python 3.9+. Код возврата 0 — всё прошло.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

STATUSES = {
    "confirmed": "Подтверждено",
    "contradicted": "Противоречит источнику",
    "clarify": "Уточните: выбор за аналитиком",
    "not_comparable": "Несопоставимо",
    "insufficient_data": "Недостаточно данных",
    "analyst_required": "Требует суждения аналитика",
}

FLAGS = ("interpretation", "sources", "conflicting", "same_scope", "same_definition")
OLD_VALUES = (None, 100)
NEW_VALUES = (None, 80, 100, 120)


# --- Реализация: последовательность условий ---------------------------------

def assign_status(x: dict) -> str:
    if x["interpretation"]:
        return "analyst_required"
    if not x["sources"]:
        return "insufficient_data"
    if x["old"] is None or x["new"] is None:
        return "insufficient_data"
    if x["conflicting"]:
        return "clarify"
    if not (x["same_scope"] and x["same_definition"]):
        return "not_comparable"
    if x["new"] < x["old"]:
        return "confirmed"
    return "contradicted"


# --- Эталон: таблица решений, правила по приоритету -------------------------
# Записана отдельно от реализации: перебор сверяет одно с другим.

DECISION_TABLE = [
    ("R1 интерпретация — только аналитик",
     lambda x: x["interpretation"], "analyst_required"),
    ("R2 нет координат источника",
     lambda x: not x["sources"], "insufficient_data"),
    ("R3 нет одного из значений",
     lambda x: None in (x["old"], x["new"]), "insufficient_data"),
    ("R4 несколько опор с разными значениями",
     lambda x: x["conflicting"], "clarify"),
    ("R5 разный периметр или определение",
     lambda x: not x["same_scope"] or not x["same_definition"], "not_comparable"),
    ("R6 значение снизилось",
     lambda x: x["new"] < x["old"], "confirmed"),
    ("R7 значение не снизилось",
     lambda x: True, "contradicted"),
]


def table_status(x: dict) -> tuple[str, str]:
    for name, cond, status in DECISION_TABLE:
        if cond(x):
            return status, name
    raise AssertionError("таблица решений неполна")


# --- Инварианты ---------------------------------------------------------------

def invariants(x: dict, status: str) -> list[str]:
    broken = []
    if status not in STATUSES:
        broken.append(f"неизвестный статус {status!r}")
    if x["interpretation"] and status != "analyst_required":
        broken.append("интерпретация решена без аналитика")
    if status == "confirmed":
        ok = (x["sources"] and not x["conflicting"] and x["same_scope"]
              and x["same_definition"] and x["old"] is not None
              and x["new"] is not None and x["new"] < x["old"])
        if not ok:
            broken.append("confirmed без всех оснований")
    if not x["sources"] and status in ("confirmed", "contradicted"):
        broken.append("вердикт без координат источника")
    if assign_status(x) != status:
        broken.append("недетерминированный результат")
    return broken


def all_inputs():
    for flags in itertools.product((False, True), repeat=len(FLAGS)):
        for old, new in itertools.product(OLD_VALUES, NEW_VALUES):
            x = dict(zip(FLAGS, flags))
            x.update(old=old, new=new)
            yield x


def normalize(inp: dict) -> dict:
    x = {f: bool(inp.get(f, False)) for f in FLAGS}
    x["old"], x["new"] = inp.get("old"), inp.get("new")
    return x


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cases_path = HERE / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    failures = 0

    # 1. Регрессионные кейсы
    reg_rows = []
    for case in cases:
        x = normalize(case["input"])
        got = assign_status(x)
        ok = got == case["expected"]
        failures += not ok
        reg_rows.append([case["name"], case["expected"], got, ok])
    reg_passed = sum(r[3] for r in reg_rows)

    # 2–3. Полный перебор и инварианты
    ex_rows, mismatches, broken_total = [], 0, 0
    for x in all_inputs():
        got = assign_status(x)
        ref, rule = table_status(x)
        broken = invariants(x, got)
        mismatches += got != ref
        broken_total += bool(broken)
        ex_rows.append([*(x[f] for f in FLAGS), x["old"], x["new"],
                        got, ref, rule, got == ref, "; ".join(broken)])
    failures += mismatches + broken_total

    with open(HERE / "results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Кейс", "Ожидаемый статус", "Полученный статус", "Совпадение"])
        w.writerows(reg_rows)

    with open(HERE / "results_exhaustive.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([*FLAGS, "old", "new", "status", "reference", "rule",
                    "match", "broken_invariants"])
        w.writerows(ex_rows)

    meta = {
        "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": platform.python_version(),
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "regression": {"passed": reg_passed, "total": len(reg_rows)},
        "exhaustive": {"combinations": len(ex_rows),
                       "mismatches_vs_table": mismatches,
                       "invariant_violations": broken_total},
        "status": "PASS" if failures == 0 else "FAIL",
    }
    (HERE / "results_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Регрессионные кейсы: {reg_passed} из {len(reg_rows)}")
    print(f"Полный перебор: {len(ex_rows)} комбинаций, "
          f"расхождений с таблицей решений: {mismatches}, "
          f"нарушений инвариантов: {broken_total}")
    print("ИТОГ:", meta["status"])
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
