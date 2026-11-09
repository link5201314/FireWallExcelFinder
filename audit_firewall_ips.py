"""離線掃描 Excel 活頁簿中的 IPv4 位址與網段。"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import logging
import re
import sys
import xml.etree.ElementTree as element_tree
import zipfile
from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TextIO

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


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
        return AddressInterval(int(network.network_address), int(network.broadcast_address))

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
                end_address = ipaddress.ip_address(".".join((*octets[:3], end_text)))
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

    rules: list[TargetRule] = []
    for line_number, raw_line in enumerate(lines, start=1):
        expression = raw_line.strip()
        if not expression or expression.startswith("#"):
            continue
        try:
            interval = parse_address_expression(expression)
        except ValueError as error:
            LOGGER.warning("目標檔第 %s 行格式錯誤，已略過：%s（%s）", line_number, expression, error)
            continue
        rules.append(TargetRule(raw_line, line_number, interval))
    return rules


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
            tokens.append(AddressToken(raw_token, interval, span_start, span_end))

    tokens.sort(key=lambda token: token.span_start)
    return tokens


def intervals_overlap(first: AddressInterval, second: AddressInterval) -> bool:
    """判斷兩個閉區間是否相交。"""
    return max(first.start, second.start) <= min(first.end, second.end)


def discover_workbooks(directory: Path, recursive: bool) -> tuple[list[Path], bool]:
    """列出符合範圍的 Excel 活頁簿並略過符號連結。"""
    absolute_directory = directory.absolute()
    path_components = (absolute_directory, *absolute_directory.parents)
    if any(component.is_symlink() for component in path_components):
        raise InputError(f"掃描目錄路徑不可包含符號連結：{directory}")
    if not directory.exists() or not directory.is_dir():
        raise InputError(f"掃描目錄不存在或不是目錄：{directory}")

    root = absolute_directory
    pending_directories = [root]
    workbooks: list[Path] = []
    partial_failure = False

    while pending_directories:
        current_directory = pending_directories.pop()
        try:
            entries = sorted(current_directory.iterdir(), key=lambda entry: entry.name.casefold())
        except OSError as error:
            LOGGER.warning("無法讀取目錄 %s，已略過：%s", current_directory, error)
            partial_failure = True
            continue

        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if recursive:
                    pending_directories.append(entry)
                continue
            if entry.name.startswith("~$") or entry.suffix.casefold() != ".xlsx":
                continue
            if entry.is_file():
                workbooks.append(entry)

    workbooks.sort(key=lambda path: str(path).casefold())
    return workbooks, partial_failure


def make_context(text: str, span_start: int, span_end: int, limit: int = 100) -> str:
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
) -> Iterator[MatchRecord]:
    """以唯讀模式逐格掃描活頁簿並產生命中紀錄。"""
    with closing(load_workbook(workbook_path, read_only=True, data_only=True)) as workbook:
        for worksheet in workbook.worksheets:
            if not worksheet_matches(worksheet.title, sheet_keywords):
                continue
            for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                for column_number, value in enumerate(row, start=1):
                    if value is None:
                        continue
                    cell_text = str(value)
                    for token in extract_address_tokens(cell_text):
                        for target in targets:
                            if not intervals_overlap(target.interval, token.interval):
                                continue
                            coordinate = f"R{row_number}C{column_number}"
                            yield MatchRecord(
                                workbook_path.relative_to(scan_root).as_posix(),
                                target,
                                token.raw,
                                worksheet.title,
                                coordinate,
                                make_context(cell_text, token.span_start, token.span_end),
                                cell_text,
                            )


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
    parser.add_argument("-s", "--sheets", nargs="+", help="工作表名稱關鍵字，可指定多個")
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示命中儲存格完整文字")
    parser.add_argument("-r", "--recursive", action="store_true", help="遞迴掃描子目錄")
    return parser


def write_match_to_csv(writer: csv.DictWriter[str], record: MatchRecord, verbose: bool) -> None:
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


def main(argv: list[str] | None = None) -> int:
    """執行 CLI 掃描流程並回傳結束狀態。"""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    parser = build_parser()
    arguments = parser.parse_args(argv)

    output_format: str | None = None
    if arguments.output is not None:
        output_format = arguments.output.suffix.casefold()
        if output_format not in {".txt", ".csv"}:
            parser.error("報告副檔名僅支援 .txt 或 .csv")

    try:
        targets = load_target_rules(arguments.target)
        workbooks, discovery_failure = discover_workbooks(arguments.dir, arguments.recursive)
    except InputError as error:
        LOGGER.error("%s", error)
        return 2

    distinct_intervals = {(target.interval.start, target.interval.end) for target in targets}
    summary = ScanSummary(
        files_scanned=len(workbooks),
        valid_target_lines=len(targets),
        distinct_intervals=len(distinct_intervals),
        partial_failure=discovery_failure,
    )

    output_stream: TextIO | None = None
    csv_writer: csv.DictWriter[str] | None = None
    scan_root = arguments.dir.absolute()
    try:
        with ExitStack() as resource_stack:
            if arguments.output is not None:
                report_encoding = "utf-8-sig" if output_format == ".csv" else "utf-8"
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

            seen_matches: set[tuple[str, str, str, int, str]] = set()
            for workbook_path in workbooks:
                try:
                    for record in scan_workbook(
                        workbook_path, scan_root, targets, arguments.sheets
                    ):
                        deduplication_key = (
                            str(workbook_path.resolve()).casefold(),
                            record.sheet,
                            record.coordinate,
                            record.target.line_number,
                            record.token,
                        )
                        if deduplication_key in seen_matches:
                            continue
                        seen_matches.add(deduplication_key)
                        if csv_writer is not None:
                            write_match_to_csv(csv_writer, record, arguments.verbose)
                        else:
                            formatted_match = format_match(record, arguments.verbose)
                            destination = output_stream if output_stream is not None else sys.stdout
                            destination.write(f"{formatted_match}\n")
                except WORKBOOK_READ_ERRORS as error:
                    LOGGER.warning("無法讀取活頁簿 %s，已略過：%s", workbook_path.name, error)
                    summary.partial_failure = True

            if output_stream is not None and output_format == ".txt":
                write_summary(output_stream, summary)
            write_summary(sys.stdout, summary)
    except OSError as error:
        LOGGER.error("無法寫入報告：%s", error)
        return 2

    return 1 if summary.partial_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
