from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.kpi_reference_service import KpiReferenceValidationError, build_kpi_reference


def test_build_kpi_reference_accepts_four_columns_and_normalizes_schema() -> None:
    result = build_kpi_reference(
        [
            {"name": "GT", "weight_percent": 40, "quantity": 90, "threshold_percent": 0},
            {"name": "LAS", "weight_percent": 40, "quantity": 128, "threshold_percent": 40},
            {"name": "LAU", "weight_percent": 20, "quantity": 64, "threshold_percent": 0},
        ]
    )
    assert result["schema_version"] == 1
    assert result["total_weight_percent"] == 100
    assert result["items"][1] == {
        "name": "LAS",
        "weight_percent": 40.0,
        "quantity": 128.0,
        "threshold_percent": 40.0,
    }


def test_build_kpi_reference_rejects_weight_sum_other_than_100() -> None:
    try:
        build_kpi_reference(
            [
                {"name": "GT", "weight_percent": 60, "quantity": 90, "threshold_percent": 0},
                {"name": "LAS", "weight_percent": 30, "quantity": 128, "threshold_percent": 40},
            ]
        )
    except KpiReferenceValidationError as error:
        assert "100%" in str(error)
    else:
        raise AssertionError("weight sum must be rejected")


def test_build_kpi_reference_rejects_duplicate_names() -> None:
    try:
        build_kpi_reference(
            [
                {"name": "GT", "weight_percent": 50, "quantity": 90, "threshold_percent": 0},
                {"name": "GT", "weight_percent": 50, "quantity": 90, "threshold_percent": 0},
            ]
        )
    except KpiReferenceValidationError as error:
        assert "повторно" in str(error)
    else:
        raise AssertionError("duplicate names must be rejected")


if __name__ == "__main__":
    test_build_kpi_reference_accepts_four_columns_and_normalizes_schema()
    test_build_kpi_reference_rejects_weight_sum_other_than_100()
    test_build_kpi_reference_rejects_duplicate_names()
    print("KPI_REFERENCE PASS")
