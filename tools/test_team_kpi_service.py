"""Regression tests for derived hierarchical KPI calculations."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.team_kpi_service import build_team_kpi_snapshot
from handlers.kpi import build_team_kpi_report, my_kpi_markup


def _source_data() -> tuple[dict, dict, dict]:
    users = {
        "101": {"name": "A One"},
        "102": {"name": "A Two"},
        "201": {"name": "R One"},
        "301": {"name": "Coordinator A"},
        "401": {"name": "Supervisor"},
    }
    groups = {
        "101": {"name": "A One", "group": "A LAMP"},
        "102": {"name": "A Two", "group": "A LAMP"},
        "201": {"name": "R One", "group": "R LAMP"},
        "301": {"name": "Coordinator A", "group": "coor A"},
        "401": {"name": "Supervisor", "group": "SPV"},
    }
    kpi_data = {
        "a one": {
            "original_name": "A One",
            "gt_plan": 100,
            "gt_fact": 80,
            "micro_plan": 100,
            "micro_las_fact": 30,
            "micro_lau_fact": 20,
                "retrafic_plan": 10,
                "retrafic_fact": 8,
                "office_hours": 20,
                "field_hours": 12,
        },
        "a two": {
            "original_name": "A Two",
            "gt_plan": 100,
            "gt_fact": 20,
            "micro_plan": 100,
            "micro_las_fact": 20,
            "micro_lau_fact": 50,
                "retrafic_plan": 20,
                "retrafic_fact": 10,
                "office_hours": 16,
                "field_hours": 16,
        },
        "r one": {
            "original_name": "R One",
            "gt_plan": 100,
            "gt_fact": 100,
            "micro_plan": 100,
            "micro_las_fact": 50,
            "micro_lau_fact": 50,
            "retrafic_plan": 10,
            "retrafic_fact": 5,
            "office_hours": 24,
            "field_hours": 20,
        },
    }
    return users, groups, kpi_data


def test_hierarchical_weighted_aggregation() -> None:
    users, groups, kpi_data = _source_data()
    snapshot = build_team_kpi_snapshot(users, groups, kpi_data, period="2026-08", calculated_at="2026-08-22T10:00:00+05:00")

    a_team = snapshot["teams"]["A LAMP"]
    assert a_team["employee_ids"] == ["101", "102"]
    assert a_team["metrics"]["gt"]["plan"] == 200
    assert a_team["metrics"]["gt"]["fact"] == 100
    assert a_team["metrics"]["gt"]["percent"] == 50.0
    assert a_team["metrics"]["microacts"]["fact"] == 120
    assert a_team["metrics"]["microacts"]["percent"] == 60.0
    assert a_team["metrics"]["retrafic"]["percent"] == 60.0

    coor_a = snapshot["manager_reports"]["coor A"]
    assert coor_a["team_keys"] == ["A LAMP"]
    assert coor_a["overall"]["percent"] == 56.0
    assert coor_a["metrics"]["work_time"]["plan"] == 128.0
    assert coor_a["metrics"]["work_time"]["fact"] == 64.0
    assert coor_a["metrics"]["work_time"]["percent"] == 50.0

    coor_r = snapshot["manager_reports"]["coor R"]
    assert coor_r["employee_count"] == 1
    assert coor_r["metrics"]["gt"]["percent"] == 100.0

    spv = snapshot["manager_reports"]["SPV"]
    assert spv["employee_count"] == 3
    assert round(spv["metrics"]["gt"]["percent"], 6) == round(200 / 300 * 100, 6)
    assert set(spv["by_team"]) == {"A LAMP", "R LAMP"}
    assert snapshot["manager_reports"]["MNG"]["employee_count"] == 3


def test_manager_kpi_menu_and_report() -> None:
    users, groups, kpi_data = _source_data()
    snapshot = build_team_kpi_snapshot(users, groups, kpi_data, period="2026-08")

    manager_buttons = {
        button.text
        for row in my_kpi_markup("SPV", admin_mode=False).inline_keyboard
        for button in row
    }
    employee_buttons = {
        button.text
        for row in my_kpi_markup("A LAMP", admin_mode=False).inline_keyboard
        for button in row
    }
    assert "📊 KPI" in manager_buttons
    assert "📊 KPI" in employee_buttons
    manager_markup = my_kpi_markup("SPV", admin_mode=False)
    employee_markup = my_kpi_markup("A LAMP", admin_mode=False)
    assert manager_markup.inline_keyboard[0][0].callback_data == "my_kpi_show_team"
    assert employee_markup.inline_keyboard[0][0].callback_data == "my_kpi_show_kpi"

    report = build_team_kpi_report(snapshot, "SPV")
    assert "Показатели KPI" in report
    assert "Руководитель: *SPV*" in report
    assert "A LAMP" in report
    assert "R LAMP" in report
    assert "Общий KPI" not in report

    coor_report = build_team_kpi_report(snapshot, "coor A")
    assert "Время работы подчинённой команды" in coor_report
    assert "План: `128.0` ч. (64 ч. на человека)" in coor_report
    assert "Общий факт: `64.0` ч." in coor_report
    assert "Факт офис: `36.0` ч." in coor_report
    assert "Факт поле: `28.0` ч." in coor_report
    assert "Время работы подчинённой команды" not in report


def test_missing_employee_kpi_is_reported_without_becoming_zero_data() -> None:
    users, groups, kpi_data = _source_data()
    del kpi_data["a two"]
    snapshot = build_team_kpi_snapshot(users, groups, kpi_data, period="2026-08")

    report = snapshot["manager_reports"]["coor A"]
    assert report["employee_count"] == 2
    assert report["quality"]["missing_employee_ids"] == ["102"]
    assert report["metrics"]["gt"]["fact"] == 80
    assert "У части сотрудников отсутствуют KPI-данные" in report["quality"]["warnings"]


if __name__ == "__main__":
    test_hierarchical_weighted_aggregation()
    test_manager_kpi_menu_and_report()
    test_missing_employee_kpi_is_reported_without_becoming_zero_data()
    print("TEAM_KPI_SERVICE PASS")
