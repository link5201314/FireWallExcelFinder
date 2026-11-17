"""應用程式路徑解析，原始碼執行與 Nuitka 打包後皆適用。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIRECTORY = "FireWallExcelFinder"
ASSETS_DIRECTORY = "assets"


def _compiled_module() -> object | None:
    """取得 Nuitka 注入的 __compiled__ 資訊；未打包時回傳 None。"""
    main_module = sys.modules.get("__main__")
    return getattr(main_module, "__compiled__", None)


def is_frozen() -> bool:
    """判斷目前是否為打包後的執行檔。"""
    return _compiled_module() is not None


def executable_path() -> Path:
    """回傳啟動的執行檔路徑；原始碼執行時回傳主腳本路徑。"""
    compiled = _compiled_module()
    if compiled is not None:
        return Path(compiled.original_argv0)
    return Path(sys.argv[0])


def application_directory() -> Path:
    """回傳程式所在目錄；打包後為執行檔所在資料夾。"""
    if is_frozen():
        return executable_path().resolve().parent
    return Path(__file__).resolve().parent


def local_app_data_directory() -> Path:
    """取得使用者本地應用程式資料目錄。"""
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path.home() / "AppData" / "Local"


def user_data_directory() -> Path:
    """回傳應用程式可寫入的資料目錄，不保證已存在。"""
    return local_app_data_directory() / APP_DIRECTORY


def ensure_user_data_directory() -> Path:
    """建立並回傳應用程式資料目錄。"""
    directory = user_data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resource_path(*parts: str) -> Path:
    """取得隨程式散布的資源檔路徑，例如 assets/app.ico。"""
    return application_directory().joinpath(*parts)
