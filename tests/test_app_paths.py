"""應用程式路徑解析測試。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import app_paths


def test_source_mode_uses_project_directory() -> None:
    assert not app_paths.is_frozen()
    assert app_paths.application_directory() == (
        Path(app_paths.__file__).resolve().parent
    )


def test_frozen_mode_uses_executable_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = tmp_path / "dist" / "FireWallExcelFinder.exe"
    executable.parent.mkdir()
    main_module = sys.modules["__main__"]
    monkeypatch.setattr(
        main_module,
        "__compiled__",
        SimpleNamespace(original_argv0=str(executable)),
        raising=False,
    )

    assert app_paths.is_frozen()
    assert app_paths.executable_path() == executable
    assert app_paths.application_directory() == executable.parent
    assert app_paths.resource_path("assets", "app.ico") == (
        executable.parent / "assets" / "app.ico"
    )


def test_user_data_directory_uses_local_app_data(
    isolated_local_app_data: Path,
) -> None:
    expected = isolated_local_app_data / app_paths.APP_DIRECTORY

    assert app_paths.user_data_directory() == expected
    assert not expected.exists()
    assert app_paths.ensure_user_data_directory() == expected
    assert expected.is_dir()


def test_ensure_user_data_directory_reports_unwritable_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocker))

    with pytest.raises(OSError):
        app_paths.ensure_user_data_directory()
