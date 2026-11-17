"""離線掃描 Excel 活頁簿中的 IPv4 位址與網段。"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import logging
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as element_tree
import zipfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO, cast

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app_logging import configure_logging

LOGGER = logging.getLogger(__name__)
IPV4_SOURCE = r"(?:\d{1,3}\.){3}\d{1,3}"
TOKEN_PATTERNS = (
    re.compile(rf"(?<![\w.]){IPV4_SOURCE}/\d+(?![\w.])"),
    re.compile(rf"(?<![\w.]){IPV4_SOURCE}-{IPV4_SOURCE}(?![\w.])"),
    re.compile(rf"(?<![\w.]){IPV4_SOURCE}-\d{{1,3}}(?![\w.])"),
    re.compile(rf"(?<![\w.]){IPV4_SOURCE}(?![\w.])"),
)
WORKBOOK_READ_ERRORS = (
    OSError,
    zipfile.BadZipFile,
    InvalidFileException,
    element_tree.ParseError,
    IndexError,
    KeyError,
    ValueError,
)
CSV_FIELDS = (
    "file",
    "sheet",
    "coordinate",
    "context",
    "token",
    "target",
    "target_line",
)


@dataclass(frozen=True)
class AddressInterval:
    """IPv4 閉區間。"""

    start: int
    end: int


@dataclass(frozen=True)
class TargetRule:
    """保留來源文字與行號的目標規則。"""

    raw: str
    line_number: int
    interval: AddressInterval


@dataclass(frozen=True)
class AddressToken:
    """從儲存格文字解析出的位址 Token。"""

    raw: str
    interval: AddressInterval
    span_start: int
    span_end: int


@dataclass(frozen=True)
class MatchRecord:
    """可追溯至活頁簿儲存格的命中紀錄。"""

    file_name: str
    target: TargetRule
    token: str
    sheet: str
    coordinate: str
    context: str
    cell_text: str


@dataclass
class ScanSummary:
    """整批掃描統計。"""

    files_scanned: int
    valid_target_lines: int
    distinct_intervals: int
    partial_failure: bool = False


@dataclass(frozen=True)
class TargetRuleIssue:
    """目標清單中無法解析的來源行。"""

    line_number: int
    raw: str
    message: str


@dataclass
class ScanOutcome:
    """背景掃描的命中、摘要及狀態。"""

    matches: list[MatchRecord]
    summary: ScanSummary
    warnings: list[str]
    cancelled: bool = False
    error: str | None = None
    report_error: str | None = None


class ScanCancelled(RuntimeError):
    """表示報告輸出在提交前收到取消要求。"""


class InputError(ValueError):
    """表示不可繼續的命令列輸入或輸出錯誤。"""


def parse_address_expression(expression: str) -> AddressInterval:
    """將 IPv4 位址、範圍或 CIDR 解析為閉區間。

    Args:
        expression: 目標規則或位址 Token 的原始文字。

    Returns:
        對應的 IPv4 閉區間。

    Raises:
        ValueError: 格式錯誤、非 IPv4 或區間反向時。
    """
    value = expression.strip()
    if not value:
        raise ValueError("位址規則不可為空")

    if "/" in value:
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as error:
            raise ValueError(f"無效的 CIDR：{value}") from error
        if network.version != 4:
            raise ValueError("僅支援 IPv4 CIDR")
        return AddressInterval(
            int(network.network_address), int(network.broadcast_address)
        )

    if "-" in value:
        if value.count("-") != 1:
            raise ValueError(f"無效的位址範圍：{value}")
        start_text, end_text = (part.strip() for part in value.split("-", 1))
        try:
            start_address = ipaddress.ip_address(start_text)
            if "." not in end_text:
                if not end_text.isdecimal():
                    raise ValueError("簡寫範圍的末碼必須是數字")
                octets = start_text.split(".")
                if len(octets) != 4:
                    raise ValueError("簡寫範圍必須從 IPv4 位址開始")
                end_address = ipaddress.ip_address(
                    ".".join((*octets[:3], end_text))
                )
                if int(end_address) >> 8 != int(start_address) >> 8:
                    raise ValueError("簡寫範圍必須位於同一個 /24")
            else:
                end_address = ipaddress.ip_address(end_text)
        except ValueError as error:
            raise ValueError(f"無效的位址範圍：{value}") from error
        if start_address.version != 4 or end_address.version != 4:
            raise ValueError("僅支援 IPv4 位址範圍")
        if int(start_address) > int(end_address):
            raise ValueError("位址範圍起始不可大於結束")
        return AddressInterval(int(start_address), int(end_address))

    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError(f"無效的 IPv4 位址：{value}") from error
    if address.version != 4:
        raise ValueError("僅支援 IPv4 位址")
    numeric_address = int(address)
    return AddressInterval(numeric_address, numeric_address)


def load_target_rules(target_path: Path) -> list[TargetRule]:
    """讀取並解析目標檔；錯誤規則會警告後略過。"""
    try:
        lines = target_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        raise InputError(f"無法讀取目標檔 {target_path}: {error}") from error

    rules, issues = parse_target_lines(lines)
    for issue in issues:
        LOGGER.warning("目標檔第 %s 行格式錯誤，已略過", issue.line_number)
    if issues:
        LOGGER.info("目標檔已載入，含有 %s 行格式錯誤", len(issues))
    else:
        LOGGER.info("目標檔已載入：%s 條有效目標規則行", len(rules))
    return rules


def parse_target_lines(
    lines: list[str],
) -> tuple[list[TargetRule], list[TargetRuleIssue]]:
    """解析目標文字行，回傳有效規則與可供介面呈現的錯誤。"""
    rules: list[TargetRule] = []
    issues: list[TargetRuleIssue] = []
    for line_number, raw_line in enumerate(lines, start=1):
        expression = raw_line.strip()
        if not expression or expression.startswith("#"):
            continue
        try:
            interval = parse_address_expression(expression)
        except ValueError as error:
            issues.append(TargetRuleIssue(line_number, raw_line, str(error)))
            continue
        rules.append(TargetRule(raw_line, line_number, interval))
    return rules, issues


def extract_address_tokens(cell_text: str) -> list[AddressToken]:
    """依 CIDR、範圍、單一 IPv4 的順序擷取儲存格 Token。"""
    normalized_text = cell_text.replace("\r", " ").replace("\n", " ")
    occupied_spans: list[tuple[int, int]] = []
    tokens: list[AddressToken] = []

    for pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(normalized_text):
            span_start, span_end = match.span()
            if any(
                span_start < occupied_end and span_end > occupied_start
                for occupied_start, occupied_end in occupied_spans
            ):
                continue
            occupied_spans.append((span_start, span_end))
            raw_token = match.group(0)
            try:
                interval = parse_address_expression(raw_token)
            except ValueError:
                continue
            tokens.append(
                AddressToken(raw_token, interval, span_start, span_end)
            )

    tokens.sort(key=lambda token: token.span_start)
    return tokens


def intervals_overlap(first: AddressInterval, second: AddressInterval) -> bool:
    """判斷兩個閉區間是否相交。"""
    return max(first.start, second.start) <= min(first.end, second.end)


def validate_scan_directory(directory: Path) -> Path:
    """驗證掃描目錄存在且路徑不包含符號連結。"""
    absolute_directory = directory.absolute()
    path_components = (
        component
        for component in (absolute_directory, *absolute_directory.parents)
        if component != Path(component.anchor)
    )
    if any(component.is_symlink() for component in path_components):
        raise InputError(f"掃描目錄路徑不可包含符號連結：{directory}")
    if not directory.exists() or not directory.is_dir():
        raise InputError(f"掃描目錄不存在或不是目錄：{directory}")
    return absolute_directory


def discover_workbooks(
    directory: Path,
    recursive: bool,
    warning_callback: Callable[[str], None] | None = None,
) -> tuple[list[Path], bool]:
    """列出符合範圍的 Excel 活頁簿並略過符號連結。"""
    absolute_directory = validate_scan_directory(directory)

    root = absolute_directory
    pending_directories = [root]
    workbooks: list[Path] = []
    partial_failure = False

    while pending_directories:
        current_directory = pending_directories.pop()
        try:
            entries = sorted(
                current_directory.iterdir(),
                key=lambda entry: entry.name.casefold(),
            )
        except OSError as error:
            warning = f"無法讀取目錄 {current_directory}，已略過：{error}"
            LOGGER.warning("%s", warning)
            if warning_callback is not None:
                warning_callback(warning)
            partial_failure = True
            continue

        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if recursive:
                    pending_directories.append(entry)
                continue
            if (
                entry.name.startswith("~$")
                or entry.suffix.casefold() != ".xlsx"
            ):
                continue
            if entry.is_file():
                workbooks.append(entry)

    workbooks.sort(key=lambda path: str(path).casefold())
    return workbooks, partial_failure


def make_context(
    text: str, span_start: int, span_end: int, limit: int = 100
) -> str:
    """擷取以 Token 為中心、長度受限的文字上下文。"""
    if len(text) <= limit:
        return text
    token_length = span_end - span_start
    available = max(0, limit - token_length)
    start = max(0, span_start - available // 2)
    end = min(len(text), start + limit)
    start = max(0, end - limit)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def worksheet_matches(sheet_name: str, keywords: list[str] | None) -> bool:
    """檢查工作表名稱是否符合任一關鍵字。"""
    if not keywords:
        return True
    folded_name = sheet_name.casefold()
    return any(keyword.casefold() in folded_name for keyword in keywords)


def scan_workbook(
    workbook_path: Path,
    scan_root: Path,
    targets: list[TargetRule],
    sheet_keywords: list[str] | None,
    cancellation_requested: Callable[[], bool] | None = None,
) -> Iterator[MatchRecord]:
    """以唯讀模式逐格掃描活頁簿並產生命中紀錄。"""
    with closing(
        load_workbook(workbook_path, read_only=True, data_only=True)
    ) as workbook:
        for worksheet in workbook.worksheets:
            if not worksheet_matches(worksheet.title, sheet_keywords):
                continue
            for row_number, row in enumerate(
                worksheet.iter_rows(values_only=True), start=1
            ):
                if (
                    cancellation_requested is not None
                    and cancellation_requested()
                ):
                    return
                for column_number, value in enumerate(row, start=1):
                    if value is None:
                        continue
                    cell_text = str(value)
                    for token in extract_address_tokens(cell_text):
                        for target in targets:
                            if not intervals_overlap(
                                target.interval, token.interval
                            ):
                                continue
                            coordinate = f"R{row_number}C{column_number}"
                            yield MatchRecord(
                                workbook_path.relative_to(
                                    scan_root
                                ).as_posix(),
                                target,
                                token.raw,
                                worksheet.title,
                                coordinate,
                                make_context(
                                    cell_text, token.span_start, token.span_end
                                ),
                                cell_text,
                            )


def scan_directory(
    directory: Path,
    targets: list[TargetRule],
    recursive: bool = False,
    sheet_keywords: list[str] | None = None,
    cancellation_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    match_callback: Callable[[MatchRecord], None] | None = None,
    collect_matches: bool = True,
) -> ScanOutcome:
    """掃描指定目錄，供 GUI 背景工作與其他呼叫端共用。"""
    sheet_description = (
        "、".join(sheet_keywords) if sheet_keywords else "全部"
    )
    LOGGER.info(
        "開始掃描：目錄=%s 遞迴=%s 工作表關鍵字=%s 選取規則數=%s",
        directory,
        "是" if recursive else "否",
        sheet_description,
        len(targets),
    )
    warnings: list[str] = []
    workbooks, discovery_failure = discover_workbooks(
        directory, recursive, warnings.append
    )
    distinct_intervals = {
        (target.interval.start, target.interval.end) for target in targets
    }
    summary = ScanSummary(
        files_scanned=len(workbooks),
        valid_target_lines=len(targets),
        distinct_intervals=len(distinct_intervals),
        partial_failure=discovery_failure,
    )
    matches: list[MatchRecord] = []
    seen_matches: set[tuple[str, str, str, int, str]] = set()
    scan_root = directory.absolute()
    total_matches = 0

    def log_cancelled(processed: int) -> None:
        LOGGER.info(
            "掃描完成：已取消 已處理=%s/%s 個檔案 命中數=%s "
            "有效目標規則行數=%s 部分失敗=%s",
            processed,
            len(workbooks),
            total_matches,
            summary.valid_target_lines,
            "是" if summary.partial_failure else "否",
        )

    for index, workbook_path in enumerate(workbooks, start=1):
        if cancellation_requested is not None and cancellation_requested():
            log_cancelled(index - 1)
            return ScanOutcome(matches, summary, warnings, cancelled=True)
        if progress_callback is not None:
            progress_callback(index - 1, len(workbooks), workbook_path.name)
        file_match_count = 0
        try:
            for record in scan_workbook(
                workbook_path,
                scan_root,
                targets,
                sheet_keywords,
                cancellation_requested,
            ):
                deduplication_key = (
                    str(workbook_path.resolve()).casefold(),
                    record.sheet,
                    record.coordinate,
                    record.target.line_number,
                    record.token,
                )
                if deduplication_key not in seen_matches:
                    seen_matches.add(deduplication_key)
                    total_matches += 1
                    file_match_count += 1
                    if collect_matches:
                        matches.append(record)
                    if match_callback is not None:
                        match_callback(record)
                if (
                    cancellation_requested is not None
                    and cancellation_requested()
                ):
                    log_cancelled(index - 1)
                    return ScanOutcome(
                        matches, summary, warnings, cancelled=True
                    )
        except WORKBOOK_READ_ERRORS as error:
            warning = f"無法讀取活頁簿 {workbook_path.name}，已略過：{error}"
            LOGGER.warning("%s", warning)
            warnings.append(warning)
            summary.partial_failure = True
        LOGGER.debug(
            "已掃描 %s：%s 筆命中", workbook_path.name, file_match_count
        )
        if progress_callback is not None:
            progress_callback(index, len(workbooks), workbook_path.name)

    LOGGER.info(
        "掃描完成：檔案數=%s 命中數=%s 有效目標規則行數=%s "
        "部分失敗=%s 已取消=否",
        summary.files_scanned,
        total_matches,
        summary.valid_target_lines,
        "是" if summary.partial_failure else "否",
    )
    return ScanOutcome(matches, summary, warnings)


def write_report(
    matches: list[MatchRecord],
    output_path: Path,
    verbose: bool,
    summary: ScanSummary,
    cancellation_requested: Callable[[], bool] | None = None,
    warnings: list[str] | None = None,
) -> None:
    """先寫入同目錄暫存檔，完成後以原子替換提交報告。"""
    suffix = output_path.suffix.casefold()
    if suffix not in {".txt", ".csv"}:
        raise InputError("報告副檔名僅支援 .txt 或 .csv")
    encoding = "utf-8-sig" if suffix == ".csv" else "utf-8"
    temporary_path: Path | None = None
    backup_path: Path | None = None
    report_warnings = warnings or []
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            if suffix == ".csv":
                writer = write_csv_header(cast(TextIO, stream))
                for record in matches:
                    if (
                        cancellation_requested is not None
                        and cancellation_requested()
                    ):
                        raise ScanCancelled("報告輸出已取消")
                    write_match_to_csv(writer, record, verbose)
            else:
                stream.write("命中明細\n")
                for record in matches:
                    if (
                        cancellation_requested is not None
                        and cancellation_requested()
                    ):
                        raise ScanCancelled("報告輸出已取消")
                    stream.write(f"{format_match(record, verbose)}\n")
                write_summary(cast(TextIO, stream), summary)
                stream.write(
                    f"部分失敗：{'是' if summary.partial_failure else '否'}\n"
                )
                for warning in report_warnings:
                    stream.write(f"警告：{warning}\n")
        if cancellation_requested is not None and cancellation_requested():
            raise ScanCancelled("報告輸出已取消")
        if suffix == ".csv" and output_path.exists():
            with tempfile.NamedTemporaryFile(
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".bak",
                delete=False,
            ) as backup:
                backup_path = Path(backup.name)
            shutil.copy2(output_path, backup_path)
        temporary_path.replace(output_path)
        temporary_path = None
        if suffix == ".csv":
            try:
                write_csv_summary(
                    output_path, summary, len(matches), report_warnings
                )
            except OSError:
                if backup_path is not None:
                    backup_path.replace(output_path)
                    backup_path = None
                else:
                    output_path.unlink(missing_ok=True)
                raise
        LOGGER.info(
            "已寫入%s報告：%s（%s 筆命中）",
            "CSV" if suffix == ".csv" else "文字",
            output_path,
            len(matches),
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if backup_path is not None:
            backup_path.unlink(missing_ok=True)


def format_match(record: MatchRecord, verbose: bool) -> str:
    """格式化一筆純文字命中紀錄。"""
    context = record.cell_text if verbose else record.context
    return (
        f"檔案：{record.file_name} | 工作表：{record.sheet} | "
        f"座標：{record.coordinate} | 目標：{record.target.raw} "
        f"（第 {record.target.line_number} 行）| Token：{record.token} | 上下文：{context}"
    )


def write_csv_header(stream: TextIO) -> csv.DictWriter[str]:
    """建立 CSV writer 並寫入欄位標題。"""
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader()
    return writer


def write_summary(stream: TextIO, summary: ScanSummary) -> None:
    """輸出掃描統計摘要。"""
    stream.write(f"掃描檔案數：{summary.files_scanned}\n")
    stream.write(f"有效目標規則行數：{summary.valid_target_lines}\n")
    stream.write(f"不同位址區間數：{summary.distinct_intervals}\n")


def build_parser() -> argparse.ArgumentParser:
    """建立 CLI 引數解析器。"""
    parser = argparse.ArgumentParser(
        description="離線掃描 Excel 活頁簿中的 IPv4 位址、範圍與 CIDR。"
    )
    parser.add_argument(
        "-d",
        "--dir",
        type=Path,
        default=Path.cwd(),
        help="Excel 檔案目錄（預設目前目錄）",
    )
    parser.add_argument(
        "-t",
        "--target",
        type=Path,
        default=Path("targets.txt"),
        help="目標規則文字檔（預設 targets.txt）",
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="報告輸出路徑（僅支援 .txt 或 .csv）"
    )
    parser.add_argument(
        "-s", "--sheets", nargs="+", help="工作表名稱關鍵字，可指定多個"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="顯示完整儲存格文字"
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true", help="遞迴掃描子目錄"
    )
    return parser


def write_match_to_csv(
    writer: csv.DictWriter[str], record: MatchRecord, verbose: bool
) -> None:
    """將命中紀錄寫入 CSV。"""
    writer.writerow(
        {
            "file": record.file_name,
            "target": record.target.raw,
            "target_line": record.target.line_number,
            "token": record.token,
            "sheet": record.sheet,
            "coordinate": record.coordinate,
            "context": record.cell_text if verbose else record.context,
        }
    )


def write_csv_summary(
    output_path: Path,
    summary: ScanSummary,
    match_count: int,
    warnings: list[str],
) -> None:
    """輸出與 CSV 配對的摘要檔，保留原 CSV 欄位相容性。"""
    summary_path = output_path.with_name(f"{output_path.name}.summary.txt")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=output_path.parent,
            prefix=f".{summary_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            write_summary(cast(TextIO, stream), summary)
            stream.write(f"命中數：{match_count}\n")
            stream.write(
                f"部分失敗：{'是' if summary.partial_failure else '否'}\n"
            )
            for warning in warnings:
                stream.write(f"警告：{warning}\n")
        temporary_path.replace(summary_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """執行 CLI 掃描流程並回傳結束狀態。"""
    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)

    output_format: str | None = None
    if arguments.output is not None:
        output_format = arguments.output.suffix.casefold()
        if output_format not in {".txt", ".csv"}:
            parser.error("報告副檔名僅支援 .txt 或 .csv")

    try:
        targets = load_target_rules(arguments.target)
        validate_scan_directory(arguments.dir)
    except InputError as error:
        LOGGER.error("%s", error)
        return 2

    output_stream: TextIO | None = None
    csv_writer: csv.DictWriter[str] | None = None
    try:
        with ExitStack() as resource_stack:
            if arguments.output is not None:
                report_encoding = (
                    "utf-8-sig" if output_format == ".csv" else "utf-8"
                )
                opened_output = resource_stack.enter_context(
                    arguments.output.open(
                        "w", encoding=report_encoding, newline=""
                    )
                )
                output_stream = opened_output
                if output_format == ".csv":
                    csv_writer = write_csv_header(opened_output)
                else:
                    opened_output.write("命中明細\n")

            def emit_match(record: MatchRecord) -> None:
                """將共用掃描流程產生的命中寫至 CLI 輸出。"""
                if csv_writer is not None:
                    write_match_to_csv(csv_writer, record, arguments.verbose)
                    return
                formatted_match = format_match(record, arguments.verbose)
                destination = (
                    output_stream if output_stream is not None else sys.stdout
                )
                destination.write(f"{formatted_match}\n")

            outcome = scan_directory(
                arguments.dir,
                targets,
                arguments.recursive,
                arguments.sheets,
                match_callback=emit_match,
                collect_matches=False,
            )
            summary = outcome.summary

            if output_stream is not None and output_format == ".txt":
                write_summary(output_stream, summary)
            write_summary(sys.stdout, summary)
    except InputError as error:
        LOGGER.error("%s", error)
        return 2
    except OSError as error:
        LOGGER.error("無法寫入報告：%s", error)
        return 2

    return 1 if summary.partial_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
