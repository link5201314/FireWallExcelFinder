"""日誌設定、輪替與 CLI 日誌行為測試。"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from openpyxl import Workbook

import app_logging

SCRIPT = Path(__file__).resolve().parents[1] / "audit_firewall_ips.py"
RunCli = Callable[..., subprocess.CompletedProcess[str]]
APP_ROOT_NAME = app_logging.APP_DIRECTORY


def make_workbook(
    path: Path, cells: dict[str, str], sheet_name: str = "正式區"
) -> None:
    """建立測試用活頁簿。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet_name
    for coordinate, value in cells.items():
        worksheet[coordinate] = value
    workbook.save(path)
    workbook.close()


def write_config(root: Path, ui: str, file_level: str = "INFO") -> Path:
    """在暫存 LOCALAPPDATA 寫入控制檔。"""
    path = root / APP_ROOT_NAME / "logging.ini"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"[levels]\nui = {ui}\nfile = {file_level}\n", encoding="utf-8"
    )
    return path


def log_file(root: Path) -> Path:
    """取得暫存 LOCALAPPDATA 下的日誌檔路徑。"""
    return (
        root
        / APP_ROOT_NAME
        / "logs"
        / "firewall_excel_finder.log"
    )


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
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    return invoke


def test_creates_control_file_with_default_levels(tmp_path: Path) -> None:
    config_path = tmp_path / APP_ROOT_NAME / "logging.ini"

    settings, problems = app_logging.load_settings(config_path)

    assert config_path.is_file()
    contents = config_path.read_text(encoding="utf-8")
    assert "[levels]" in contents
    assert "ui = WARNING" in contents
    assert "file = INFO" in contents
    assert settings.ui_level == logging.WARNING
    assert settings.file_level == logging.INFO
    assert problems == []


def test_parses_level_names_case_insensitively(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.ini"
    config_path.write_text(
        "[levels]\nui = debug\nfile = Error\n", encoding="utf-8"
    )

    settings, problems = app_logging.load_settings(config_path)

    assert settings.ui_level == logging.DEBUG
    assert settings.file_level == logging.ERROR
    assert problems == []


def test_invalid_level_falls_back_and_reports_problem(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.ini"
    config_path.write_text(
        "[levels]\nui = 很吵\nfile = INFO\n", encoding="utf-8"
    )

    settings, problems = app_logging.load_settings(config_path)

    assert settings.ui_level == logging.WARNING
    assert settings.file_level == logging.INFO
    assert any("ui" in problem for problem in problems)


def test_empty_level_value_falls_back_and_reports_problem(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "logging.ini"
    config_path.write_text("[levels]\nui =\nfile =\n", encoding="utf-8")

    settings, problems = app_logging.load_settings(config_path)

    assert settings == app_logging.LoggingSettings()
    assert len(problems) == 2


def test_broken_ini_falls_back_to_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.ini"
    config_path.write_text("這不是 INI\n\x00壞掉", encoding="utf-8")

    settings, problems = app_logging.load_settings(config_path)

    assert settings == app_logging.LoggingSettings()
    assert problems


def test_unknown_sections_and_keys_are_ignored(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.ini"
    config_path.write_text(
        "[levels]\nui = INFO\nfile = WARNING\nextra = 忽略\n"
        "[unknown]\nkey = value\n",
        encoding="utf-8",
    )

    settings, problems = app_logging.load_settings(config_path)

    assert settings.ui_level == logging.INFO
    assert settings.file_level == logging.WARNING
    assert problems == []


def test_writes_utf8_messages_with_timestamp_and_logger(
    tmp_path: Path,
) -> None:
    paths = app_logging.LoggingPaths(
        config_path=tmp_path / "logging.ini",
        log_path=tmp_path / "logs" / "firewall_excel_finder.log",
    )

    app_logging.configure_logging(paths=paths)
    logging.getLogger("測試記錄").info("中文訊息")
    app_logging.shutdown_logging()

    contents = paths.log_path.read_text(encoding="utf-8")
    assert "中文訊息" in contents
    assert re.search(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} INFO 測試記錄: 中文訊息$",
        contents,
        flags=re.MULTILINE,
    )


def test_file_level_filters_messages(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.ini"
    config_path.write_text(
        "[levels]\nui = DEBUG\nfile = ERROR\n", encoding="utf-8"
    )
    paths = app_logging.LoggingPaths(
        config_path=config_path,
        log_path=tmp_path / "logs" / "firewall_excel_finder.log",
    )

    app_logging.configure_logging(paths=paths)
    logging.getLogger("測試記錄").info("一般訊息")
    logging.getLogger("測試記錄").error("只有錯誤")
    app_logging.shutdown_logging()

    contents = paths.log_path.read_text(encoding="utf-8")
    assert "只有錯誤" in contents
    assert "一般訊息" not in contents


def test_rotation_creates_backup_and_starts_new_file(
    tmp_path: Path,
    isolated_local_app_data: Path,
    run_cli: RunCli,
) -> None:
    paths = log_file(isolated_local_app_data)
    paths.parent.mkdir(parents=True)
    paths.write_bytes(b"x" * (app_logging.MAX_BYTES + 1))
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.7.7"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.7.7\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    backup = paths.with_name(f"{paths.name}.1")
    assert backup.is_file()
    assert backup.stat().st_size > app_logging.MAX_BYTES
    contents = paths.read_text(encoding="utf-8")
    assert "日誌設定：" in contents
    assert paths.stat().st_size < app_logging.MAX_BYTES


def test_cli_writes_scan_lifecycle_to_log_file(
    tmp_path: Path,
    isolated_local_app_data: Path,
    run_cli: RunCli,
) -> None:
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.7.7"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.7.7\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    contents = log_file(isolated_local_app_data).read_text(encoding="utf-8")
    assert "日誌設定：" in contents
    assert "開始掃描：目錄=" in contents
    assert "掃描完成：檔案數=1" in contents


def test_cli_shows_effective_settings_when_ui_allows_info(
    tmp_path: Path,
    isolated_local_app_data: Path,
    run_cli: RunCli,
) -> None:
    write_config(isolated_local_app_data, "INFO")
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.7.7"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.7.7\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "日誌設定：" in result.stderr
    assert "ui=INFO" in result.stderr


def test_cli_does_not_log_cell_text_or_invalid_target_line(
    tmp_path: Path,
    isolated_local_app_data: Path,
    run_cli: RunCli,
) -> None:
    make_workbook(
        tmp_path / "rules.xlsx",
        {"A1": "機密內容 192.168.7.7"},
    )
    target_path = tmp_path / "targets.txt"
    target_path.write_text(
        "192.168.7.7\n機密目標規則 999.1.1.1\n", encoding="utf-8"
    )

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    contents = log_file(isolated_local_app_data).read_text(encoding="utf-8")
    assert "機密內容" not in contents
    assert "機密目標規則" not in contents


def test_cli_uses_defaults_when_control_file_is_broken(
    tmp_path: Path,
    isolated_local_app_data: Path,
    run_cli: RunCli,
) -> None:
    config_path = isolated_local_app_data / APP_ROOT_NAME / "logging.ini"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("壞掉的設定\n[levels\n", encoding="utf-8")
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.7.7"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.7.7\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "使用預設等級" in result.stderr
    assert log_file(isolated_local_app_data).is_file()


def test_missing_local_app_data_falls_back_to_home_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(
        Path, "home", classmethod(lambda cls: tmp_path / "home")
    )

    result = app_logging.local_app_data_directory()

    assert result == tmp_path / "home" / "AppData" / "Local"


def test_cli_scans_when_local_app_data_is_undefined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli: RunCli,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.7.7"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.7.7\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "192.168.7.7" in result.stdout
    fallback_log = (
        home
        / "AppData"
        / "Local"
        / app_logging.APP_DIRECTORY
        / "logs"
        / "firewall_excel_finder.log"
    )
    assert fallback_log.is_file()


def test_cli_scans_even_when_log_directory_cannot_be_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli: RunCli,
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocker))
    make_workbook(tmp_path / "rules.xlsx", {"A1": "192.168.7.7"})
    target_path = tmp_path / "targets.txt"
    target_path.write_text("192.168.7.7\n", encoding="utf-8")

    result = run_cli("-d", str(tmp_path), "-t", str(target_path))

    assert result.returncode == 0, result.stderr
    assert "192.168.7.7" in result.stdout
    assert "日誌" in result.stderr


def run_script(
    tmp_path: Path, source: str
) -> subprocess.CompletedProcess[str]:
    """在獨立程序中執行最小腳本，讓例外真的觸發 hook。"""
    script_path = tmp_path / "crash_driver.py"
    script_path.write_text(source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_uncaught_exception_is_logged_with_traceback(
    tmp_path: Path,
    isolated_local_app_data: Path,
) -> None:
    source = (
        "import sys\n"
        f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
        "from app_logging import configure_logging\n"
        "configure_logging()\n"
        'raise RuntimeError("崩潰測試")\n'
    )

    result = run_script(tmp_path, source)

    assert result.returncode == 1
    contents = log_file(isolated_local_app_data).read_text(encoding="utf-8")
    assert "CRITICAL" in contents
    assert "未捕捉例外" in contents
    assert "Traceback" in contents
    assert "崩潰測試" in contents


def test_background_thread_exception_is_logged_as_critical(
    tmp_path: Path,
    isolated_local_app_data: Path,
) -> None:
    source = (
        "import sys\n"
        "import threading\n"
        f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
        "from app_logging import configure_logging\n"
        "configure_logging()\n"
        "def boom():\n"
        '    raise ValueError("執行緒崩潰測試")\n'
        "thread = threading.Thread(target=boom)\n"
        "thread.start()\n"
        "thread.join()\n"
    )

    result = run_script(tmp_path, source)

    assert result.returncode == 0
    contents = log_file(isolated_local_app_data).read_text(encoding="utf-8")
    assert "CRITICAL" in contents
    assert "背景執行緒未捕捉例外" in contents
    assert "ValueError" in contents
    assert "執行緒崩潰測試" in contents
