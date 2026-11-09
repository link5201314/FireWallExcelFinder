"""CLI 外部行為測試。"""

from __future__ import annotations

import csv
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from openpyxl import Workbook


SCRIPT = Path(__file__).resolve().parents[1] / "audit_firewall_ips.py"
RunCli = Callable[..., subprocess.CompletedProcess[str]]


def make_workbook(path: Path, cells: dict[str, str], sheet_name: str = "正式區") -> None:
    """建立測試用活頁簿。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    for coordinate, value in cells.items():
        worksheet[coordinate] = value
    workbook.save(path)
    workbook.close()


@pytest.fixture
def run_cli(tmp_path: Path) -> RunCli:
    """提供在隔離目錄執行 CLI 的測試 helper。"""

    def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=tmp_path,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )

    return invoke


def test_scans_single_ip_and_reports_cell_coordinate(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(
        tmp_path / "rules.xlsx",
        {"A1": "允許來源 192.168.0.10", "B2": "其他資料"},
    )
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.0.10\n", encoding="utf-8")

    result = run_cli("--dir", str(tmp_path), "--target", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "rules.xlsx" in result.stdout
    assert "正式區" in result.stdout
    assert "R1C1" in result.stdout
    assert "掃描檔案數：1" in result.stdout


def test_uses_current_directory_and_default_target_file(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.1.1"})
    (tmp_path / "targets.txt").write_text("192.168.1.1\n", encoding="utf-8")

    result = run_cli()

    assert result.returncode == 0, result.stderr
    assert "rules.xlsx" in result.stdout


def test_matches_cidr_and_full_or_abbreviated_ranges_by_overlap(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(
        tmp_path / "rules.xlsx",
        {
            "A1": "來源 192.168.1.10-25",
            "A2": "網段 192.168.1.24/29",
            "A3": "埠群組 10.0.0.6-8",
        },
    )
    target_path = tmp_path / "targets.txt"
    target_path.write_text(
        "192.168.1.20-30\n"
        "10.0.0.4-10.0.0.8\n"
        "10.0.0.4-8\n"
        "192.168.1.3/24\n",
        encoding="utf-8",
    )

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "192.168.1.10-25" in result.stdout
    assert "192.168.1.24/29" in result.stdout
    assert "10.0.0.6-8" in result.stdout
    assert "10.0.0.4-8" in result.stdout
    assert "192.168.1.3/24" in result.stdout


def test_accepts_utf8_bom_and_skips_invalid_target_lines(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.2.10"})
    target_contents = (
        "\ufeff# 目標清單\n"
        "999.1.1.1\n"
        "192.168.0.250-10\n"
        "192.168.2.10\n"
    )
    target_path = tmp_path / "targets.txt"
    target_path.write_bytes(target_contents.encode("utf-8"))

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "192.168.2.10" in result.stdout
    assert "第 2 行" in result.stderr
    assert "第 3 行" in result.stderr
    assert "有效目標規則行數：1" in result.stdout


def test_preserves_original_target_rule_text(tmp_path: Path, run_cli: RunCli) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.12.1"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text(" 192.168.12.1 \n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "目標： 192.168.12.1 " in result.stdout


def test_normalizes_newlines_in_cell_text(tmp_path: Path, run_cli: RunCli) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "來源\r\n192.168.3.8\n備註"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.3.8\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "192.168.3.8" in result.stdout


def test_recursive_scan_and_sheet_keyword_filter(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "top.xlsx", {"A1": "192.168.4.1"})
    make_workbook(
        tmp_path / "nested" / "nested.xlsx",
        {"A1": "192.168.4.2"},
        sheet_name="Production Nested",
    )
    workbook = Workbook()
    matching = workbook.active
    matching.title = "Production Zone"
    matching["A1"] = "192.168.4.3"
    nonmatching = workbook.create_sheet("Testing")
    nonmatching["A1"] = "192.168.4.4"
    workbook.save(tmp_path / "top.xlsx")
    workbook.close()
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.4.0/24\n", encoding="utf-8")

    default_result = run_cli("-d", str(tmp_path), "-t", str(target_path))
    assert default_result.returncode == 0, default_result.stderr
    assert "nested.xlsx" not in default_result.stdout

    result = run_cli(
        "-d",
        str(tmp_path),
        "-t",
        str(target_path),
        "-r",
        "-s",
        "production",
        "不存在",
    )

    assert result.returncode == 0, result.stderr
    assert "nested.xlsx" in result.stdout
    assert "Production Zone" in result.stdout
    assert "Testing" not in result.stdout


def test_skips_symbolic_linked_workbooks(tmp_path: Path, run_cli: RunCli) -> None:
    source = tmp_path / "rules.xlsx"
    make_workbook(source, {"A1": "192.168.4.9"})
    nested_directory = tmp_path / "nested"
    nested_workbook = nested_directory / "nested.xlsx"
    make_workbook(nested_workbook, {"A1": "192.168.4.9"})
    try:
        (tmp_path / "linked.xlsx").symlink_to(source)
        (tmp_path / "linked-directory").symlink_to(
            nested_directory, target_is_directory=True
        )
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"目前環境無法建立符號連結：{error}")
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.4.9\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path), "-r")

    assert result.returncode == 0, result.stderr
    assert "linked.xlsx" not in result.stdout
    assert "linked-directory" not in result.stdout
    assert "掃描檔案數：2" in result.stdout


def test_rejects_scan_path_with_symbolic_link_ancestor(
    tmp_path: Path, run_cli: RunCli
) -> None:
    actual_directory = tmp_path / "actual"
    make_workbook(
        actual_directory / "nested" / "rules.xlsx", {"A1": "192.168.4.10"}
    )
    linked_directory = tmp_path / "linked-root"
    try:
        linked_directory.symlink_to(actual_directory, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"目前環境無法建立符號連結：{error}")
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.4.10\n", encoding="utf-8")

    result = run_cli(
        "-d", str(linked_directory / "nested"), "-t", str(target_path)
    )

    assert result.returncode == 2
    assert "符號連結" in result.stderr


def test_ignores_excel_lock_files(tmp_path: Path, run_cli: RunCli) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.5.1"})
    (tmp_path / "~$open.xlsx").write_text("not an Excel workbook", encoding="utf-8")
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.5.1\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "~$open.xlsx" not in result.stderr
    assert "掃描檔案數：1" in result.stdout


def test_writes_csv_matches_while_printing_summary_to_console(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.6.1"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.6.1\n", encoding="utf-8")
    output = tmp_path / "report.csv"

    result = run_cli("-d", str(tmp_path), "-t", str(target_path), "-o", str(output))

    assert result.returncode == 0, result.stderr
    assert "有效目標規則行數：1" in result.stdout
    assert "rules.xlsx" not in result.stdout
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    assert output.read_text(encoding="utf-8-sig").splitlines()[0] == (
        "file,sheet,coordinate,context,token,target,target_line"
    )
    with output.open(encoding="utf-8-sig", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert len(rows) == 1
    assert rows[0]["file"] == "rules.xlsx"
    assert rows[0]["coordinate"] == "R1C1"


def test_csv_report_distinguishes_same_filename_in_different_directories(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "east" / "rules.xlsx", {"A1": "192.168.13.1"})
    make_workbook(tmp_path / "west" / "rules.xlsx", {"A1": "192.168.13.2"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.13.0/24\n", encoding="utf-8")
    output = tmp_path / "report.csv"

    result = run_cli(
        "-d", str(tmp_path), "-t", str(target_path), "-r", "-o", str(output)
    )

    assert result.returncode == 0, result.stderr
    with output.open(encoding="utf-8-sig", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert {row["file"] for row in rows} == {"east/rules.xlsx", "west/rules.xlsx"}


def test_writes_text_report_with_summary_and_match_context(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "來源 192.168.6.10-20 備註"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.6.15\n", encoding="utf-8")
    output = tmp_path / "report.txt"

    result = run_cli("-d", str(tmp_path), "-t", str(target_path), "-o", str(output))

    assert result.returncode == 0, result.stderr
    report = output.read_text(encoding="utf-8")
    assert "rules.xlsx" in report
    assert "192.168.6.10-20" in report
    assert "有效目標規則行數：1" in report
    assert "有效目標規則行數：1" in result.stdout


def test_verbose_displays_full_cell_text(tmp_path: Path, run_cli: RunCli) -> None:
    full_text = "前文" + ("x" * 80) + " 192.168.7.1 " + ("y" * 80) + "後文"
    make_workbook(tmp_path / "rules.xlsx", {"A1": full_text})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.7.1\n", encoding="utf-8")

    brief = run_cli("-d", str(tmp_path), "-t", str(target_path))
    verbose = run_cli("-d", str(tmp_path), "-t", str(target_path), "-v")

    assert brief.returncode == 0, brief.stderr
    assert verbose.returncode == 0, verbose.stderr
    assert "後文" not in brief.stdout
    assert full_text in verbose.stdout


def test_deduplicates_same_target_token_and_cell(tmp_path: Path, run_cli: RunCli) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.8.1；192.168.8.1"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.8.1\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("Token：192.168.8.1") == 1


def test_preserves_identical_rules_from_distinct_source_lines(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.8.1"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.8.1\n192.168.8.1\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("Token：192.168.8.1") == 2
    assert "第 1 行" in result.stdout
    assert "第 2 行" in result.stdout


def test_invalid_long_cidr_does_not_fall_back_to_single_ip(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.14.1/999"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.14.1\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "Token：" not in result.stdout


def test_invalid_workbook_is_skipped_and_returns_partial_failure(
    tmp_path: Path, run_cli: RunCli
) -> None:
    make_workbook(tmp_path / "valid.xlsx", {"A1": "192.168.9.1"})
    (tmp_path / "broken.xlsx").write_bytes(b"not a zip workbook")
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.9.1\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 1
    assert "broken.xlsx" in result.stderr
    assert "valid.xlsx" in result.stdout


def test_invalid_scan_directory_returns_error_status(
    tmp_path: Path, run_cli: RunCli
) -> None:
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.10.1\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path / "missing"), "-t", str(target_path))

    assert result.returncode == 2
    assert result.stderr


def test_rejects_unsupported_report_extension(tmp_path: Path, run_cli: RunCli) -> None:
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.10.1\n", encoding="utf-8")

    result = run_cli(
        "-d", str(tmp_path), "-t", str(target_path), "-o", str(tmp_path / "report.json")
    )

    assert result.returncode == 2
    assert ".txt" in result.stderr
    assert ".csv" in result.stderr
