from __future__ import annotations

import pytest

from research_director.retry_policy import classify_exception, get_retry_delay, should_retry


@pytest.mark.parametrize(
    "error_type,expected",
    [
        ("file_unreadable", True),
        ("temporary_missing_data", True),
        ("provider_unavailable", True),
        ("FileNotFoundError", True),
        ("PermissionError", True),
        ("missing_required_fields", False),
        ("pytest_failed", False),
        ("gate_blocked", False),
        ("ValueError", False),
        ("", False),
    ],
)
def test_should_retry(error_type, expected):
    assert should_retry(error_type) is expected


def test_get_retry_delay_is_exponential_capped():
    assert get_retry_delay(1) == 1
    assert get_retry_delay(2) == 2
    assert get_retry_delay(3) == 4
    assert get_retry_delay(6) == 30


def test_classify_exception_covers_required_categories():
    assert classify_exception(FileNotFoundError("x")) == "file_unreadable"
    assert classify_exception(PermissionError("x")) == "file_unreadable"
    assert classify_exception(TimeoutError("x")) == "provider_unavailable"
    assert classify_exception(ConnectionError("x")) == "provider_unavailable"
    assert classify_exception(ValueError("缺少必需字段: ['odds_home']")) == "missing_required_fields"
    assert classify_exception(ValueError("空数据：CSV 无任何记录")) == "temporary_missing_data"

