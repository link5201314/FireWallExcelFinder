"""CLI 外部行為測試。"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook


SCRIPT = Path(__file__).resolve().parents[1] / "audit_firewall_ips.py"


class AuditFirewallIpsCliTests(unittest.TestCase):
    """驗證防火牆 Excel 位址掃描器的命令列行為。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_workbook(
        self,
        path: Path,
        cells: dict[str, str],
        sheet_name: str = "正式區",
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet_name
        for coordinate, value in cells.items():
            worksheet[coordinate] = value
        workbook.save(path)
        workbook.close()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=self.root,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
        )

    def test_scans_single_ip_and_reports_cell_coordinate(self) -> None:
        self.make_workbook(
            self.root / "rules.xlsx",
            {"A1": "允許來源 192.168.0.10", "B2": "其他資料"},
        )
        (self.root / "targets.txt").write_text("192.168.0.10\n", encoding="utf-8")

        result = self.run_cli("--dir", str(self.root), "--target", str(self.root / "targets.txt"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rules.xlsx", result.stdout)
        self.assertIn("正式區", result.stdout)
        self.assertIn("R1C1", result.stdout)
        self.assertIn("掃描檔案數：1", result.stdout)

    def test_uses_current_directory_and_default_target_file(self) -> None:
        self.make_workbook(self.root / "rules.xlsx", {"A1": "192.168.1.1"})
        (self.root / "targets.txt").write_text("192.168.1.1\n", encoding="utf-8")

        result = self.run_cli()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rules.xlsx", result.stdout)

    def test_matches_cidr_and_full_or_abbreviated_ranges_by_overlap(self) -> None:
        self.make_workbook(
            self.root / "rules.xlsx",
            {
                "A1": "來源 192.168.1.10-25",
                "A2": "網段 192.168.1.24/29",
                "A3": "埠群組 10.0.0.6-8",
            },
        )
        (self.root / "targets.txt").write_text(
            "192.168.1.20-30\n"
            "10.0.0.4-10.0.0.8\n"
            "10.0.0.4-8\n"
            "192.168.1.3/24\n",
            encoding="utf-8",
        )

        result = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("192.168.1.10-25", result.stdout)
        self.assertIn("192.168.1.24/29", result.stdout)
        self.assertIn("10.0.0.6-8", result.stdout)
        self.assertIn("10.0.0.4-8", result.stdout)
        self.assertIn("192.168.1.3/24", result.stdout)

    def test_accepts_utf8_bom_and_skips_invalid_target_lines(self) -> None:
        self.make_workbook(self.root / "rules.xlsx", {"A1": "192.168.2.10"})
        target_contents = (
            "\ufeff# 目標清單\n"
            "999.1.1.1\n"
            "192.168.0.250-10\n"
            "192.168.2.10\n"
        )
        (self.root / "targets.txt").write_bytes(target_contents.encode("utf-8"))

        result = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("192.168.2.10", result.stdout)
        self.assertIn("第 2 行", result.stderr)
        self.assertIn("第 3 行", result.stderr)
        self.assertIn("有效目標規則行數：1", result.stdout)

    def test_normalizes_newlines_in_cell_text(self) -> None:
        self.make_workbook(self.root / "rules.xlsx", {"A1": "來源\r\n192.168.3.8\n備註"})
        (self.root / "targets.txt").write_text("192.168.3.8\n", encoding="utf-8")

        result = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("192.168.3.8", result.stdout)

    def test_recursive_scan_and_sheet_keyword_filter(self) -> None:
        base = self.root / "top.xlsx"
        self.make_workbook(base, {"A1": "192.168.4.1"})
        nested = self.root / "nested" / "nested.xlsx"
        self.make_workbook(nested, {"A1": "192.168.4.2"}, sheet_name="Production Nested")
        workbook = Workbook()
        matching = workbook.active
        matching.title = "Production Zone"
        matching["A1"] = "192.168.4.3"
        nonmatching = workbook.create_sheet("Testing")
        nonmatching["A1"] = "192.168.4.4"
        workbook.save(base)
        workbook.close()
        (self.root / "targets.txt").write_text("192.168.4.0/24\n", encoding="utf-8")

        default_result = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))
        self.assertEqual(default_result.returncode, 0, default_result.stderr)
        self.assertNotIn("nested.xlsx", default_result.stdout)

        result = self.run_cli(
            "-d",
            str(self.root),
            "-t",
            str(self.root / "targets.txt"),
            "-r",
            "-s",
            "production",
            "不存在",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nested.xlsx", result.stdout)
        self.assertIn("Production Zone", result.stdout)
        self.assertNotIn("Testing", result.stdout)

    def test_skips_symbolic_linked_workbooks(self) -> None:
        source = self.root / "rules.xlsx"
        self.make_workbook(source, {"A1": "192.168.4.9"})
        link = self.root / "linked.xlsx"
        nested_directory = self.root / "nested"
        nested_directory.mkdir()
        nested_workbook = nested_directory / "nested.xlsx"
        self.make_workbook(nested_workbook, {"A1": "192.168.4.9"})
        linked_directory = self.root / "linked-directory"
        try:
            link.symlink_to(source)
            linked_directory.symlink_to(nested_directory, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"目前環境無法建立符號連結：{error}")
        (self.root / "targets.txt").write_text("192.168.4.9\n", encoding="utf-8")

        result = self.run_cli(
            "-d", str(self.root), "-t", str(self.root / "targets.txt"), "-r"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("linked.xlsx", result.stdout)
        self.assertNotIn("linked-directory", result.stdout)
        self.assertIn("掃描檔案數：2", result.stdout)

    def test_ignores_excel_lock_files(self) -> None:
        self.make_workbook(self.root / "rules.xlsx", {"A1": "192.168.5.1"})
        (self.root / "~$open.xlsx").write_text("not an Excel workbook", encoding="utf-8")
        (self.root / "targets.txt").write_text("192.168.5.1\n", encoding="utf-8")

        result = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("~$open.xlsx", result.stderr)
        self.assertIn("掃描檔案數：1", result.stdout)

    def test_writes_csv_matches_while_printing_summary_to_console(self) -> None:
        self.make_workbook(self.root / "rules.xlsx", {"A1": "192.168.6.1"})
        (self.root / "targets.txt").write_text("192.168.6.1\n", encoding="utf-8")
        output = self.root / "report.csv"

        result = self.run_cli(
            "-d", str(self.root), "-t", str(self.root / "targets.txt"), "-o", str(output)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("命中紀錄數：1", result.stdout)
        self.assertNotIn("rules.xlsx", result.stdout)
        with output.open(encoding="utf-8", newline="") as report_file:
            rows = list(csv.DictReader(report_file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file"], "rules.xlsx")
        self.assertEqual(rows[0]["coordinate"], "R1C1")

    def test_writes_text_report_with_summary_and_match_context(self) -> None:
        self.make_workbook(self.root / "rules.xlsx", {"A1": "來源 192.168.6.10-20 備註"})
        (self.root / "targets.txt").write_text("192.168.6.15\n", encoding="utf-8")
        output = self.root / "report.txt"

        result = self.run_cli(
            "-d", str(self.root), "-t", str(self.root / "targets.txt"), "-o", str(output)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        report = output.read_text(encoding="utf-8")
        self.assertIn("rules.xlsx", report)
        self.assertIn("192.168.6.10-20", report)
        self.assertIn("命中紀錄數：1", report)
        self.assertIn("命中紀錄數：1", result.stdout)

    def test_verbose_displays_full_cell_text(self) -> None:
        full_text = "前文" + ("x" * 80) + " 192.168.7.1 " + ("y" * 80) + "後文"
        self.make_workbook(self.root / "rules.xlsx", {"A1": full_text})
        (self.root / "targets.txt").write_text("192.168.7.1\n", encoding="utf-8")

        brief = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))
        verbose = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"), "-v")

        self.assertEqual(brief.returncode, 0, brief.stderr)
        self.assertEqual(verbose.returncode, 0, verbose.stderr)
        self.assertNotIn("後文", brief.stdout)
        self.assertIn(full_text, verbose.stdout)

    def test_deduplicates_same_target_token_and_cell(self) -> None:
        self.make_workbook(self.root / "rules.xlsx", {"A1": "192.168.8.1；192.168.8.1"})
        (self.root / "targets.txt").write_text("192.168.8.1\n", encoding="utf-8")

        result = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("命中紀錄數：1", result.stdout)

    def test_invalid_workbook_is_skipped_and_returns_partial_failure(self) -> None:
        self.make_workbook(self.root / "valid.xlsx", {"A1": "192.168.9.1"})
        (self.root / "broken.xlsx").write_bytes(b"not a zip workbook")
        (self.root / "targets.txt").write_text("192.168.9.1\n", encoding="utf-8")

        result = self.run_cli("-d", str(self.root), "-t", str(self.root / "targets.txt"))

        self.assertEqual(result.returncode, 1)
        self.assertIn("broken.xlsx", result.stderr)
        self.assertIn("valid.xlsx", result.stdout)

    def test_invalid_scan_directory_returns_error_status(self) -> None:
        target = self.root / "targets.txt"
        target.write_text("192.168.10.1\n", encoding="utf-8")

        result = self.run_cli("-d", str(self.root / "missing"), "-t", str(target))

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr)

    def test_rejects_unsupported_report_extension(self) -> None:
        target = self.root / "targets.txt"
        target.write_text("192.168.10.1\n", encoding="utf-8")

        result = self.run_cli(
            "-d", str(self.root), "-t", str(target), "-o", str(self.root / "report.json")
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn(".txt", result.stderr)
        self.assertIn(".csv", result.stderr)


if __name__ == "__main__":
    unittest.main()