from __future__ import annotations

from datetime import date

import pytest

from sourcecode.capabilities import CapabilityError, default_registry
from sourcecode.tools import (
    calculate,
    copy_file,
    current_datetime,
    date_shift,
    file_sha256,
    query_csv,
    write_text_file,
)


def test_calculate_supports_useful_arithmetic_without_code_execution():
    assert calculate("round(sum([19.5, 20.5, 10]) / 3, 2)")["result"] == 16.67
    with pytest.raises(ValueError):
        calculate("__import__('os').getcwd()")
    with pytest.raises(ValueError):
        calculate("2 ** 100")


def test_write_and_hash_stay_inside_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("S17_SANDBOX_ROOT", str(tmp_path))
    written = write_text_file("reports/result.txt", "verified output")
    assert written["sha256"] == file_sha256("reports/result.txt")["sha256"]
    with pytest.raises(FileExistsError):
        write_text_file("reports/result.txt", "replacement")
    with pytest.raises(PermissionError):
        write_text_file("../escape.txt", "no")


def test_current_datetime_uses_iana_timezone():
    result = current_datetime("Asia/Kolkata")
    assert date.fromisoformat(result["date"])
    assert result["utc_offset"] == "+0530"
    assert date_shift("2026-09-18", -14)["result"] == "2026-09-04"


def test_copy_file_is_byte_preserving(monkeypatch, tmp_path):
    monkeypatch.setenv("S17_SANDBOX_ROOT", str(tmp_path))
    (tmp_path / "source.bin").write_bytes(b"a\x00b\n")
    result = copy_file("source.bin", "nested/copy.bin")
    assert result["match"] is True
    assert (tmp_path / "nested/copy.bin").read_bytes() == b"a\x00b\n"


def test_query_csv_joins_and_aggregates_without_write_authority(monkeypatch, tmp_path):
    monkeypatch.setenv("S17_SANDBOX_ROOT", str(tmp_path))
    (tmp_path / "left.csv").write_text("id,value\na,3\nb,5\n")
    (tmp_path / "right.csv").write_text("id,multiplier\na,10\nb,4\n")
    result = query_csv(["left.csv", "right.csv"],
                       "SELECT l.id, CAST(l.value AS INT) * CAST(r.multiplier AS INT) total "
                       "FROM left l JOIN right r USING(id) ORDER BY l.id")
    assert result["rows"] == [{"id": "a", "total": 30}, {"id": "b", "total": 20}]
    with pytest.raises(ValueError):
        query_csv(["left.csv"], "DROP TABLE left")


def test_registry_validates_generic_tool_contracts():
    registry = default_registry()
    assert registry.validate("write_file", {"path": "x.txt", "content": "x"})["overwrite"] is False
    with pytest.raises(CapabilityError):
        registry.validate("write_file", {"path": "x.txt", "content": "x", "overwrite": "yes"})
