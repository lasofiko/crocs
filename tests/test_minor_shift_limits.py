from __future__ import annotations

import pandas as pd
import pytest

from crocs.services.minor_shift_limits import (
    age_completed_on_reference,
    compute_staff_caps,
    effective_shift_cap_hours,
    minor_max_shift_hours,
)


def test_minor_max_shift_hours_boundaries() -> None:
    assert minor_max_shift_hours(13) is None
    assert minor_max_shift_hours(14) == 4.0
    assert minor_max_shift_hours(15) == 4.0  # min(4,5)
    assert minor_max_shift_hours(16) == 5.0  # min(5,7)
    assert minor_max_shift_hours(17) == 7.0
    assert minor_max_shift_hours(18) == 7.0
    assert minor_max_shift_hours(19) is None


def test_effective_shift_cap_merges_file_and_age() -> None:
    assert effective_shift_cap_hours(8.0, 15) == 4.0
    assert effective_shift_cap_hours(3.0, 15) == 3.0
    assert effective_shift_cap_hours(None, 17) == 7.0
    assert effective_shift_cap_hours(24.0, 25) == 24.0


def test_age_completed_on_reference() -> None:
    ref = pd.Timestamp("2026-06-15")
    assert age_completed_on_reference(ref, pd.Timestamp("2008-06-14")) == 18
    assert age_completed_on_reference(ref, pd.Timestamp("2008-06-16")) == 17


def test_compute_staff_caps_age_column() -> None:
    sl = pd.DataFrame(
        {
            "employee_id": ["1"],
            "age": [15],
            "shift_limit": [8.0],
        },
    )
    wc, sc = compute_staff_caps(sl, pd.Timestamp("2026-01-01"))
    assert wc == {}
    assert sc["1"] == 4.0


def test_compute_staff_caps_birth_date() -> None:
    sl = pd.DataFrame(
        {
            "employee_id": ["1"],
            "birth_date": ["2010-07-01"],
        },
    )
    wc, sc = compute_staff_caps(sl, pd.Timestamp("2026-06-15"))
    assert sc["1"] == pytest.approx(4.0)

