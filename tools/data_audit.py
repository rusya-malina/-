from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
JSON_FILES = [
    "users.json",
    "kpi_data.json",
    "plans_config.json",
    "pending_requests.json",
    "team_requests.json",
    "teams.json",
    "issuance_data.json",
    "user_requests.json",
]


def main() -> None:
    print("DATA AUDIT")
    for filename in JSON_FILES:
        path = ROOT / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"{filename}: records={len(data)} type={type(data).__name__}")
        if filename == "kpi_data.json":
            bad = []
            required = {"gt_plan", "gt_fact", "micro_las_fact", "micro_lau_fact", "retrafic_plan", "retrafic_fact"}
            for name, record in data.items():
                if not isinstance(record, dict) or not required.issubset(record):
                    bad.append(name)
            print(f"  KPI schema invalid={len(bad)}")
        if filename == "issuance_data.json":
            print(f"  schema_version={data.get('_schema_version')}")
            bad = [key for key, record in data.items() if key != "_schema_version" and not isinstance(record, dict)]
            print(f"  issuance record invalid={len(bad)}")
        if filename in {"team_requests.json", "teams.json"}:
            labels = [record.get("team") for record in data.values() if isinstance(record, dict)]
            print(f"  team_labels={sorted(set(labels))}")

    workbook = ROOT / "XLS Worksheet.xlsx"
    if workbook.exists():
        excel = pd.ExcelFile(workbook)
        print(f"Excel sheets={excel.sheet_names}")
        for sheet in excel.sheet_names:
            frame = pd.read_excel(workbook, sheet_name=sheet, dtype=object)
            print(f"  {sheet}: rows={len(frame)} columns={list(frame.columns)}")
    else:
        print("Excel template missing")


if __name__ == "__main__":
    main()
