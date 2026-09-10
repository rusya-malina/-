from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from handlers.kpi import _coordinator_team_balances


def main() -> None:
    users = {"10": "Coor A", "20": "Coor R", "11": "A User", "12": "R User"}
    groups = {
        "10": {"group": "coor A"},
        "20": {"group": "coor R"},
        "11": {"group": "A LAMP"},
        "12": {"group": "R LAMP"},
    }
    kpi = {
        "coor a": {"micro_las_fact": 999, "micro_lau_fact": 999, "gt_fact": 999},
        "coor r": {"micro_las_fact": 888, "micro_lau_fact": 888, "gt_fact": 888},
        "a user": {"micro_las_fact": 2, "micro_lau_fact": 3, "gt_fact": 4},
        "r user": {"micro_las_fact": 20, "micro_lau_fact": 30, "gt_fact": 40},
    }
    issuance = {
        "_schema_version": 2,
        "11": {"name": "A User", "mints_issued": 10, "sticks_issued": 20},
        "12": {"name": "R User", "mints_issued": 100, "sticks_issued": 200},
    }
    group, count, a = _coordinator_team_balances("10", "coor A", users, groups, kpi, issuance)
    assert group == "A LAMP" and count == 1
    assert a["mints_issued"] == 10 and a["sticks_issued"] == 20
    assert a["mints_used"] == 5 and a["sticks_used"] == 4
    group, count, r = _coordinator_team_balances("20", "coor R", users, groups, kpi, issuance)
    assert group == "R LAMP" and count == 1
    assert r["mints_issued"] == 100 and r["sticks_issued"] == 200
    assert r["mints_used"] == 50 and r["sticks_used"] == 40

    zeroed_issuance = {
        "_schema_version": 2,
        "11": {"name": "A User", "mints_issued": 0, "sticks_issued": 0},
    }
    zeroed_kpi = {"a user": {"micro_las_fact": 999, "micro_lau_fact": 999, "gt_fact": 999}}
    group, count, zeroed = _coordinator_team_balances("10", "coor A", users, groups, zeroed_kpi, zeroed_issuance)
    assert group == "A LAMP" and count == 1
    assert zeroed["sticks_issued"] == 0
    assert zeroed["sticks_used"] == 0
    assert zeroed["sticks_balance"] == 0
    assert zeroed["mints_used"] == 0
    assert zeroed["mints_balance"] == 0
    print("coordinator balance hierarchy tests passed")


if __name__ == "__main__":
    main()
