"""應用程式日誌設定、輪替檔案與未捕捉例外鉤子。"""

from __future__ import annotations

import configparser
import logging
import logging.handlers
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from app_paths import APP_DIRECTORY, local_app_data_directory

CONFIG_FILE_NAME = "logging.ini"
LOG_DIRECTORY_NAME = "logs"
LOG_FILE_NAME = "firewall_excel_finder.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3
DEFAULT_UI_LEVEL = logging.WARNING
DEFAULT_FILE_LEVEL = logging.INFO
LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LEVELS_SECTION = "levels"
UI_KEY = "ui"
FILE_KEY = "file"

CONFIG_TEMPLATE = """\
# FireWallExcelFinder 日誌設定
# 等級可為 DEBUG、INFO、WARNING、ERROR、CRITICAL（不分大小寫）。
# ui：GUI「日誌」分頁與 CLI console（stderr）的輸出等級。
# file：日誌檔的輸出等級。
# 修改後需重新啟動程式才會生效。

[levels]
ui = WARNING
file = INFO
"""

LOGGER = logging.getLogger(__name__)
_installed_handlers: list[logging.Handler] = []


@dataclass(frozen=True)
class LoggingPaths:
    """控制檔與日誌檔的實際位置。"""

    config_path: Path
    log_path: Path


@dataclass(frozen=True)
class LoggingSettings:
    """UI sink 與檔案 sink 各自的等級。"""

    ui_level: int = DEFAULT_UI_LEVEL
    file_level: int = DEFAULT_FILE_LEVEL


@dataclass(frozen=True)
class LoggingSetup:
    """一次初始化後的有效設定與降級狀態。"""

    settings: LoggingSettings
    paths: LoggingPaths
    file_enabled: bool


def default_paths() -> LoggingPaths:
    """依目前環境變數計算預設控制檔與日誌檔位置。"""
    root = local_app_data_directory() / APP_DIRECTORY
    return LoggingPaths(
        config_path=root / CONFIG_FILE_NAME,
        log_path=root / LOG_DIRECTORY_NAME / LOG_FILE_NAME,
    )


def parse_level(value: str | None, default: int) -> tuple[int, bool]:
    """解析等級名稱；回傳等級與是否為合法值。"""
    if value is None:
        return default, True
    normalized = value.strip().upper()
    if not normalized:
        return default, False
    if normalized not in LEVEL_NAMES:
        return default, False
    return logging.getLevelName(normalized), True


def load_settings(config_path: Path) -> tuple[LoggingSettings, list[str]]:
    """讀取控制檔；任何問題都退回預設值並回傳警告訊息。"""
    problems: list[str] = []
    _ensure_config_file(config_path, problems)
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except (configparser.Error, UnicodeError, OSError) as error:
        problems.append(
            f"無法讀取日誌控制檔 {config_path}，使用預設等級：{error}"
        )
        return LoggingSettings(), problems

    if not parser.has_section(LEVELS_SECTION):
        problems.append(
            f"日誌控制檔 {config_path} 缺少 [{LEVELS_SECTION}] 區段，"
            "使用預設等級"
        )
        return LoggingSettings(), problems

    ui_value = parser.get(LEVELS_SECTION, UI_KEY, fallback=None)
    file_value = parser.get(LEVELS_SECTION, FILE_KEY, fallback=None)
    ui_level, ui_valid = parse_level(ui_value, DEFAULT_UI_LEVEL)
    file_level, file_valid = parse_level(file_value, DEFAULT_FILE_LEVEL)
    if not ui_valid:
        problems.append(
            f"日誌控制檔的 ui 等級無效（{ui_value!r}），使用預設值 "
            f"{logging.getLevelName(DEFAULT_UI_LEVEL)}"
        )
    if not file_valid:
        problems.append(
            f"日誌控制檔的 file 等級無效（{file_value!r}），使用預設值 "
            f"{logging.getLevelName(DEFAULT_FILE_LEVEL)}"
        )
    if ui_value is None:
        problems.append("日誌控制檔缺少 ui 等級，使用預設值")
    if file_value is None:
        problems.append("日誌控制檔缺少 file 等級，使用預設值")
    return LoggingSettings(ui_level, file_level), problems


def _ensure_config_file(config_path: Path, problems: list[str]) -> None:
    """控制檔不存在時建立含預設值與註解的版本。"""
    if config_path.is_file():
        return
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    except OSError as error:
        problems.append(
            f"無法建立日誌控制檔 {config_path}，使用預設等級：{error}"
        )


def configure_logging(
    ui_handler: logging.Handler | None = None,
    *,
    paths: LoggingPaths | None = None,
) -> LoggingSetup:
    """建立 UI 與檔案 sink，並安裝未捕捉例外鉤子。

    可重複呼叫；每次都會先移除本程式先前安裝的 handler。
    """
    resolved_paths = paths or default_paths()
    settings, problems = load_settings(resolved_paths.config_path)
    _remove_installed_handlers()

    root = logging.getLogger()
    root.setLevel(min(settings.ui_level, settings.file_level))
    formatter = logging.Formatter(LOG_FORMAT)

    file_enabled = True
    file_error: str | None = None
    try:
        resolved_paths.log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            resolved_paths.log_path,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as error:
        file_enabled = False
        file_error = (
            f"無法建立日誌檔 {resolved_paths.log_path}，已停用檔案日誌："
            f"{error}"
        )
    else:
        file_handler.setFormatter(formatter)
        file_handler.setLevel(settings.file_level)
        _install_handler(file_handler)

    if ui_handler is not None:
        ui_handler.setFormatter(formatter)
        ui_handler.setLevel(settings.ui_level)
        _install_handler(ui_handler)
    else:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(settings.ui_level)
        _install_handler(stream_handler)

    if file_error is not None:
        LOGGER.error("%s", file_error)
    for problem in problems:
        LOGGER.warning("%s", problem)

    setup = LoggingSetup(settings, resolved_paths, file_enabled)
    LOGGER.info(
        "日誌設定：ui=%s file=%s 檔案=%s（控制檔=%s）",
        logging.getLevelName(settings.ui_level),
        logging.getLevelName(settings.file_level),
        resolved_paths.log_path if file_enabled else "停用",
        resolved_paths.config_path,
    )
    install_excepthooks()
    return setup


def detach_handler(handler: logging.Handler) -> None:
    """移除單一由本程式安裝的 handler。"""
    if handler in _installed_handlers:
        _installed_handlers.remove(handler)
    logging.getLogger().removeHandler(handler)
    handler.close()


def shutdown_logging() -> None:
    """移除並關閉本程式目前安裝的所有 handler。

    供程式結束與測試隔離使用，可安全重複呼叫。
    """
    _remove_installed_handlers()


def _install_handler(handler: logging.Handler) -> None:
    """加入 root logger 並記錄，供下次初始化清理。"""
    logging.getLogger().addHandler(handler)
    _installed_handlers.append(handler)


def _remove_installed_handlers() -> None:
    """移除並關閉本程式先前安裝的 handler。"""
    root = logging.getLogger()
    while _installed_handlers:
        handler = _installed_handlers.pop()
        root.removeHandler(handler)
        handler.close()


def install_excepthooks() -> None:
    """把未捕捉例外寫入目前可用的日誌 sink。"""

    def handle_uncaught(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: object,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        LOGGER.critical(
            "未捕捉例外",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def handle_thread_uncaught(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        LOGGER.critical(
            "背景執行緒未捕捉例外",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        threading.__excepthook__(args)

    sys.excepthook = handle_uncaught
    threading.excepthook = handle_thread_uncaught
