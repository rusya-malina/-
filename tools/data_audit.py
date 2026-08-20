from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
JSON_FILES = [
    "users.json",
    "groups.json",
    "registration_drafts.json",
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
        if filename == "users.json":
            invalid = [
                user_id for user_id, record in data.items()
                if not isinstance(record, dict) or record.get("schema_version") != 1 or not record.get("name")
            ]
            print(f"  user_schema_invalid={len(invalid)}")
        if filename == "kpi_data.json":
            bad = []
            required = {"gt_plan", "gt_fact", "micro_las_fact", "micro_lau_fact", "retrafic_plan", "retrafic_fact"}
            for name, record in data.items():
                if not isinstance(record, dict) or not required.issubset(record):
                    bad.append(name)
            print(f"  KPI schema invalid={len(bad)}")
        if filename == "issuance_data.json":
            print(f"  schema_version={data.get('_schema_version')}")
            bad = [
                key for key, record in data.items()
                if key != "_schema_version" and (not isinstance(record, dict) or record.get("schema_version") != 1)
            ]
            print(f"  issuance record invalid={len(bad)}")
        if filename in {"pending_requests.json", "team_requests.json", "user_requests.json", "teams.json"}:
            expected_kind = {
                "pending_requests.json": "registration",
                "team_requests.json": "team",
                "user_requests.json": "user",
                "teams.json": None,
            }[filename]
            invalid = [
                key for key, record in data.items()
                if not isinstance(record, dict) or record.get("schema_version") != 1
                or (expected_kind is not None and record.get("kind") != expected_kind)
            ]
            print(f"  canonical_schema_invalid={len(invalid)}")
        if filename in {"team_requests.json", "teams.json"}:
            labels = [record.get("team") for record in data.values() if isinstance(record, dict)]
            print(f"  team_labels={sorted(set(labels))}")
        if filename == "groups.json":
            allowed = {"A LAMP", "R LAMP", "coor A", "coor R", "SPV", "MNG"}
            invalid = [
                user_id for user_id, record in data.items()
                if not isinstance(record, dict) or record.get("group") not in allowed or not record.get("name")
            ]
            print(f"  group_schema_invalid={len(invalid)}")
        if filename == "registration_drafts.json":
            invalid = [user_id for user_id, record in data.items() if not isinstance(record, dict) or not record.get("name")]
            print(f"  draft_schema_invalid={len(invalid)}")

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
