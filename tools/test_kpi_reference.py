from __future__ import annotations

import math
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
        message = str(error)
        assert "ровно 100%" in message
        assert "Сейчас: 90.00%" in message
        assert "не хватает 10.00 процентных пунктов" in message
        assert "загрузите файл повторно" in message
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


def test_build_kpi_reference_allows_missing_threshold() -> None:
    result = build_kpi_reference(
        [
            {"name": "GT", "weight_percent": 60, "quantity": 90},
            {"name": "LAS", "weight_percent": 40, "quantity": 128, "threshold_percent": 40},
        ]
    )
    assert "threshold_percent" not in result["items"][0]
    assert result["items"][1]["threshold_percent"] == 40.0


def test_build_kpi_reference_allows_blank_threshold_per_row() -> None:
    result = build_kpi_reference(
        [
            {"name": "GT", "weight_percent": 50, "quantity": 90, "threshold_percent": ""},
            {"name": "LAU", "weight_percent": 50, "quantity": 64, "threshold_percent": None},
        ]
    )
    assert all("threshold_percent" not in item for item in result["items"])


def test_build_kpi_reference_allows_pandas_nan_threshold() -> None:
    result = build_kpi_reference(
        [
            {"name": "GT", "weight_percent": 100, "quantity": 90, "threshold_percent": math.nan},
        ]
    )
    assert "threshold_percent" not in result["items"][0]


if __name__ == "__main__":
    test_build_kpi_reference_accepts_four_columns_and_normalizes_schema()
    test_build_kpi_reference_rejects_weight_sum_other_than_100()
    test_build_kpi_reference_rejects_duplicate_names()
    test_build_kpi_reference_allows_missing_threshold()
    test_build_kpi_reference_allows_blank_threshold_per_row()
    test_build_kpi_reference_allows_pandas_nan_threshold()
    print("KPI_REFERENCE PASS")
