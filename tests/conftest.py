"""測試共用設定。"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

import app_logging

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_local_app_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """把 LOCALAPPDATA 導向暫存目錄，避免污染真實使用者設定。"""
    root = tmp_path / "localappdata"
    root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(root))
    yield root
    app_logging.shutdown_logging()
    logging.getLogger().setLevel(app_logging.DEFAULT_UI_LEVEL)
