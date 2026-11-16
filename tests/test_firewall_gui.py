"""GUI 使用者流程整合測試。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TypeVar, cast

import pytest
from openpyxl import Workbook
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from firewall_gui import MainWindow

WidgetType = TypeVar("WidgetType", bound=QWidget)


def get_widget(
    window: QWidget, widget_type: type[WidgetType], name: str
) -> WidgetType:
    """取得命名控制項，缺少時立即讓測試失敗。"""
    result = window.findChild(widget_type, name)
    assert result is not None, f"找不到 Qt 控制項：{name}"
    return result


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """提供整個測試工作階段共用的 Qt 應用程式。"""
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return cast(QApplication, application)


def make_workbook(
    path: Path, address: str, sheet_name: str = "正式區"
) -> None:
    """建立測試用活頁簿。"""
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet_name
    worksheet["A1"] = f"來源 {address} 備註"
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    workbook.close()


def make_window(
    qapp: QApplication, tmp_path: Path, targets: str
) -> MainWindow:
    """建立載入目標規則檔並設定掃描目錄的主視窗。"""
    target_path = tmp_path / "targets.txt"
    target_path.write_text(targets, encoding="utf-8")
    window = MainWindow()
    get_widget(window, QLineEdit, "scan_directory_input").setText(
        str(tmp_path)
    )
    get_widget(window, QLineEdit, "target_file_input").setText(
        str(target_path)
    )
    get_widget(window, QPushButton, "load_targets_button").click()
    window.show()
    qapp.processEvents()
    return window


def wait_for_signal(spy: QSignalSpy, message: str) -> None:
    """輪詢事件迴圈並等待訊號，避免阻塞背景工作執行緒。"""
    deadline = time.monotonic() + 15
    while spy.count() == 0:
        assert time.monotonic() < deadline, message
        QTest.qWait(10)


def wait_for_scan(spy: QSignalSpy) -> None:
    """等待掃描完成訊號。"""
    wait_for_signal(spy, "GUI 掃描未在期限內完成")


def wait_for_render(spy: QSignalSpy) -> None:
    """等待非同步掃描結果樹完成呈現。"""
    wait_for_signal(spy, "GUI 掃描結果樹未在期限內完成建構")


def tree_texts(tree: QTreeWidget) -> list[str]:
    """取得樹狀檢視中所有節點文字。"""
    texts: list[str] = []

    def visit(item: QTreeWidgetItem) -> None:
        texts.append(item.text(0))
        for index in range(item.childCount()):
            child = item.child(index)
            assert child is not None
            visit(child)

    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        assert item is not None
        visit(item)
    return texts


def close_window_discarding_changes(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """在隔離測試中明確選擇捨棄未儲存目標修改。"""
    monkeypatch.setattr(
        "firewall_gui.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )
    dispose_window(window)


def dispose_window(window: MainWindow) -> None:
    """關閉並釋放視窗，處理 Qt 延遲刪除事件。"""
    window.close()
    window.deleteLater()
    QApplication.processEvents()


def test_gui_scans_and_displays_file_location_tree(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "# targets\n192.168.10.8\n")
    tree = get_widget(window, QTreeWidget, "results_tree")

    spy = QSignalSpy(window.scan_finished)
    rendered = QSignalSpy(window.results_rendered)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)
    wait_for_render(rendered)

    assert "檔案：rules.xlsx" in tree_texts(tree)
    assert "工作表：正式區" in tree_texts(tree)
    assert "座標：R1C1" in tree_texts(tree)
    assert any(
        text.startswith("目標第 2 行：192.168.10.8")
        for text in tree_texts(tree)
    )
    assert "命中數：1" in get_widget(window, QLabel, "summary_label").text()
    dispose_window(window)


def test_gui_saves_edited_targets_before_scanning_and_preserves_line_numbers(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    target_path = tmp_path / "targets.txt"
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    editor = get_widget(window, QPlainTextEdit, "target_editor")
    editor.setPlainText("# updated\n\n192.168.10.8\n")
    report_path = tmp_path / "report.csv"
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(2)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )

    spy = QSignalSpy(window.scan_finished)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)

    assert (
        target_path.read_text(encoding="utf-8")
        == "# updated\n\n192.168.10.8\n"
    )
    report = report_path.read_text(encoding="utf-8-sig")
    assert "192.168.10.8" in report
    assert ",3\n" in report
    dispose_window(window)


def test_gui_target_view_groups_matches_by_source_rule(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "east.xlsx", "192.168.10.8")
    make_workbook(tmp_path / "west.xlsx", "192.168.10.9")
    window = make_window(qapp, tmp_path, "# targets\n192.168.10.0/24\n")
    tree = get_widget(window, QTreeWidget, "results_tree")

    spy = QSignalSpy(window.scan_finished)
    rendered = QSignalSpy(window.results_rendered)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)
    wait_for_render(rendered)
    rendered = QSignalSpy(window.results_rendered)
    get_widget(window, QComboBox, "view_mode_combo").setCurrentIndex(1)
    wait_for_render(rendered)

    assert tree.topLevelItemCount() == 1
    root = tree.topLevelItem(0)
    assert root is not None
    assert root.text(0) == "目標第 2 行：192.168.10.0/24"
    assert root.childCount() == 2
    children = [root.child(index) for index in range(root.childCount())]
    assert all(child is not None for child in children)
    assert {child.text(0) for child in children if child is not None} == {
        "檔案：east.xlsx",
        "檔案：west.xlsx",
    }
    east_file = next(
        child
        for child in children
        if child is not None and child.text(0) == "檔案：east.xlsx"
    )
    sheet = east_file.child(0)
    assert sheet is not None
    assert sheet.text(0) == "工作表：正式區"
    coordinate = sheet.child(0)
    assert coordinate is not None
    assert coordinate.text(0) == "座標：R1C1"
    detail = coordinate.child(0)
    assert detail is not None
    assert detail.text(0).startswith("目標第 2 行：192.168.10.0/24")
    assert "Token：192.168.10.8" in detail.text(0)
    assert "上下文：來源 192.168.10.8 備註" in detail.text(0)
    assert spy.count() == 1
    get_widget(window, QPushButton, "collapse_all_button").click()
    assert not root.isExpanded()
    get_widget(window, QPushButton, "expand_all_button").click()
    assert root.isExpanded()
    assert spy.count() == 1
    dispose_window(window)


def test_invalid_target_rows_are_visible_and_not_selectable(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    editor = get_widget(window, QPlainTextEdit, "target_editor")
    editor.setPlainText("192.168.10.8\ninvalid-target\n")
    qapp.processEvents()
    rules = get_widget(window, QListWidget, "rule_selection_list")

    invalid_item = rules.item(1)
    assert invalid_item is not None
    assert "第 2 行" in invalid_item.text()
    assert "格式錯誤" in invalid_item.text()
    assert not (invalid_item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
    close_window_discarding_changes(window, monkeypatch)


def test_scan_uses_only_checked_target_rules(
    qapp: QApplication, tmp_path: Path
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet["A1"] = "192.168.10.8"
    worksheet["A2"] = "192.168.10.9"
    workbook.save(tmp_path / "rules.xlsx")
    workbook.close()
    window = make_window(qapp, tmp_path, "192.168.10.8\n192.168.10.9\n")
    rules = get_widget(window, QListWidget, "rule_selection_list")
    second_rule = rules.item(1)
    assert second_rule is not None
    second_rule.setCheckState(Qt.CheckState.Unchecked)
    report_path = tmp_path / "selected.csv"
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(2)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )

    spy = QSignalSpy(window.scan_finished)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)

    rows = report_path.read_text(encoding="utf-8-sig").splitlines()
    assert len(rows) == 2
    assert "192.168.10.8" in rows[1]
    assert "192.168.10.9" not in rows[1]
    assert report_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert (
        "本次選取規則數：1"
        in get_widget(window, QLabel, "summary_label").text()
    )
    target_path = tmp_path / "targets.txt"
    assert target_path.read_text(encoding="utf-8") == (
        "192.168.10.8\n192.168.10.9\n"
    )
    dispose_window(window)


def test_gui_applies_recursive_sheet_filter_and_verbose_context(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "top.xlsx", "192.168.10.8", "Testing")
    full_text = "前文" + ("x" * 120) + " 192.168.10.8 " + ("y" * 120) + "後文"
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = "Production Zone"
    worksheet["A1"] = full_text
    nested_path = tmp_path / "nested" / "nested.xlsx"
    nested_path.parent.mkdir(parents=True)
    workbook.save(nested_path)
    workbook.close()
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    get_widget(window, QLineEdit, "worksheet_keywords_input").setText(
        "production"
    )
    get_widget(window, QCheckBox, "recursive_checkbox").setChecked(True)
    get_widget(window, QCheckBox, "verbose_checkbox").setChecked(True)
    report_path = tmp_path / "filtered.csv"
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(2)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )

    spy = QSignalSpy(window.scan_finished)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)

    report = report_path.read_text(encoding="utf-8-sig")
    assert "nested/nested.xlsx" in report
    assert "Production Zone" in report
    assert full_text in report
    assert "top.xlsx" not in report
    dispose_window(window)


def test_cancelled_save_does_not_start_scan(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    get_widget(window, QLineEdit, "target_file_input").clear()
    get_widget(window, QPlainTextEdit, "target_editor").setPlainText(
        "192.168.10.8\n"
    )
    monkeypatch.setattr(
        "firewall_gui.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: ("", ""),
    )

    get_widget(window, QPushButton, "start_scan_button").click()
    qapp.processEvents()

    assert not window.scan_active
    assert "儲存" in get_widget(window, QLabel, "status_label").text()
    close_window_discarding_changes(window, monkeypatch)


def test_gui_shows_empty_state_and_partial_workbook_warning(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "valid.xlsx", "192.168.10.1")
    (tmp_path / "broken.xlsx").write_bytes(b"not an xlsx workbook")
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    report_path = tmp_path / "partial.csv"
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(2)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )
    spy = QSignalSpy(window.scan_finished)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)

    assert get_widget(window, QLabel, "empty_results_label").isVisible()
    assert "部分失敗：是" in get_widget(window, QLabel, "summary_label").text()
    assert (
        "broken.xlsx"
        in get_widget(window, QPlainTextEdit, "warnings_view").toPlainText()
    )
    report_summary = Path(f"{report_path}.summary.txt").read_text(
        encoding="utf-8"
    )
    assert "部分失敗：是" in report_summary
    assert "broken.xlsx" in report_summary
    dispose_window(window)


def test_gui_cancels_scan_without_committing_partial_report(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "a-match.xlsx", "192.168.10.8")
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    for row_number in range(1, 20_001):
        worksheet.cell(row=row_number, column=1, value="no address")
    workbook.save(tmp_path / "z-large.xlsx")
    workbook.close()
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    report_path = tmp_path / "existing.csv"
    report_path.write_text("existing complete report", encoding="utf-8")
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(2)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )
    spy = QSignalSpy(window.scan_finished)
    cancellation_sent = False
    cancel_timer = QTimer(window)
    cancel_timer.setInterval(10)

    def cancel_after_first_workbook() -> None:
        nonlocal cancellation_sent
        if "z-large.xlsx" in get_widget(window, QLabel, "status_label").text():
            cancellation_sent = True
            cancel_timer.stop()
            get_widget(window, QPushButton, "cancel_scan_button").click()

    cancel_timer.timeout.connect(cancel_after_first_workbook)

    get_widget(window, QPushButton, "start_scan_button").click()
    cancel_timer.start()
    wait_for_scan(spy)

    assert cancellation_sent
    assert spy.at(0)[0] is True
    assert (
        report_path.read_text(encoding="utf-8") == "existing complete report"
    )
    assert "已取消" in get_widget(window, QLabel, "summary_label").text()
    assert (
        get_widget(window, QTreeWidget, "results_tree").topLevelItemCount()
        == 0
    )
    dispose_window(window)


def test_gui_report_summary_failure_preserves_previous_csv(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    report_path = tmp_path / "report.csv"
    report_path.write_text("previous complete report", encoding="utf-8")
    Path(f"{report_path}.summary.txt").mkdir()
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(2)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )
    spy = QSignalSpy(window.scan_finished)

    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)

    assert "無法寫入報告" in get_widget(window, QLabel, "status_label").text()
    assert (
        report_path.read_text(encoding="utf-8") == "previous complete report"
    )
    assert (
        get_widget(window, QTreeWidget, "results_tree").topLevelItemCount()
        == 1
    )
    assert "命中數：1" in get_widget(window, QLabel, "summary_label").text()
    dispose_window(window)


def test_gui_loads_bom_targets_and_preserves_actual_line_numbers(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    target_path = tmp_path / "targets.txt"
    target_path.write_bytes(
        "\ufeff# 目標清單\n\n192.168.10.8\n".encode("utf-8")
    )
    report_path = tmp_path / "bom.csv"
    window = MainWindow()
    get_widget(window, QLineEdit, "scan_directory_input").setText(
        str(tmp_path)
    )
    get_widget(window, QLineEdit, "target_file_input").setText(
        str(target_path)
    )
    get_widget(window, QPushButton, "load_targets_button").click()
    editor = get_widget(window, QPlainTextEdit, "target_editor")
    assert editor.toPlainText() == "# 目標清單\n\n192.168.10.8\n"
    rules = get_widget(window, QListWidget, "rule_selection_list")
    assert rules.count() == 1
    rule_item = rules.item(0)
    assert rule_item is not None
    assert "第 3 行" in rule_item.text()
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(2)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )

    spy = QSignalSpy(window.scan_finished)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)

    rows = report_path.read_text(encoding="utf-8-sig").splitlines()
    assert len(rows) == 2
    assert rows[1].endswith(",3")
    dispose_window(window)


def test_gui_blocks_scan_without_valid_target_rules(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "invalid-target\n")

    get_widget(window, QPushButton, "start_scan_button").click()
    qapp.processEvents()

    assert not window.scan_active
    assert "沒有有效" in get_widget(window, QLabel, "status_label").text()
    dispose_window(window)


def test_gui_blocks_scan_without_selected_target_rules(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    rules = get_widget(window, QListWidget, "rule_selection_list")
    only_rule = rules.item(0)
    assert only_rule is not None
    only_rule.setCheckState(Qt.CheckState.Unchecked)

    get_widget(window, QPushButton, "start_scan_button").click()
    qapp.processEvents()

    assert not window.scan_active
    assert "沒有已選取" in get_widget(window, QLabel, "status_label").text()
    dispose_window(window)


def test_gui_reports_invalid_scan_directory(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    get_widget(window, QLineEdit, "scan_directory_input").setText(
        str(tmp_path / "missing")
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        "firewall_gui.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(str(args[2])),
    )

    get_widget(window, QPushButton, "start_scan_button").click()
    qapp.processEvents()

    assert not window.scan_active
    assert warnings
    assert "不存在" in get_widget(window, QLabel, "status_label").text()
    dispose_window(window)


def test_gui_saves_as_new_target_file(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    editor = get_widget(window, QPlainTextEdit, "target_editor")
    editor.setPlainText("# 另存\n192.168.10.8\n")
    get_widget(window, QLineEdit, "target_file_input").clear()
    new_path = tmp_path / "saved-targets"
    monkeypatch.setattr(
        "firewall_gui.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(new_path), "文字檔 (*.txt)"),
    )

    get_widget(window, QPushButton, "save_targets_as_button").click()

    saved_path = tmp_path / "saved-targets.txt"
    assert saved_path.read_text(encoding="utf-8") == "# 另存\n192.168.10.8\n"
    assert get_widget(window, QLineEdit, "target_file_input").text() == str(
        saved_path
    )
    dispose_window(window)


def test_gui_save_failure_does_not_start_scan(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    target_directory = tmp_path / "targets.txt"
    target_directory.unlink()
    target_directory.mkdir()
    get_widget(window, QLineEdit, "target_file_input").setText(
        str(target_directory)
    )

    get_widget(window, QPushButton, "start_scan_button").click()
    qapp.processEvents()

    assert not window.scan_active
    assert "無法儲存" in get_widget(window, QLabel, "status_label").text()
    dispose_window(window)


def test_gui_reports_target_file_read_error(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    get_widget(window, QLineEdit, "target_file_input").setText(
        str(tmp_path / "missing.txt")
    )

    get_widget(window, QPushButton, "load_targets_button").click()
    qapp.processEvents()

    assert "無法載入" in get_widget(window, QLabel, "status_label").text()
    dispose_window(window)


def test_gui_scans_without_report_and_with_txt_report(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(qapp, tmp_path, "192.168.10.8\n")
    tree = get_widget(window, QTreeWidget, "results_tree")

    first_spy = QSignalSpy(window.scan_finished)
    rendered = QSignalSpy(window.results_rendered)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(first_spy)
    wait_for_render(rendered)
    assert tree.topLevelItemCount() == 1
    assert not list(tmp_path.glob("report*"))

    report_path = tmp_path / "report.txt"
    get_widget(window, QComboBox, "report_format_combo").setCurrentIndex(1)
    get_widget(window, QLineEdit, "report_path_input").setText(
        str(report_path)
    )
    second_spy = QSignalSpy(window.scan_finished)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(second_spy)

    report = report_path.read_text(encoding="utf-8")
    assert "命中明細" in report
    assert "有效目標規則行數：1" in report
    assert "部分失敗：否" in report
    dispose_window(window)


def test_gui_file_location_tree_merges_shared_nodes(
    qapp: QApplication, tmp_path: Path
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = "正式區"
    worksheet["A1"] = "來源 192.168.10.8 與 192.168.10.9"
    workbook.save(tmp_path / "rules.xlsx")
    workbook.close()
    window = make_window(qapp, tmp_path, "192.168.10.8\n192.168.10.9\n")
    tree = get_widget(window, QTreeWidget, "results_tree")

    spy = QSignalSpy(window.scan_finished)
    rendered = QSignalSpy(window.results_rendered)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)
    wait_for_render(rendered)

    assert tree.topLevelItemCount() == 1
    file_item = tree.topLevelItem(0)
    assert file_item is not None
    assert file_item.text(0) == "檔案：rules.xlsx"
    assert file_item.childCount() == 1
    sheet_item = file_item.child(0)
    assert sheet_item is not None
    assert sheet_item.text(0) == "工作表：正式區"
    assert sheet_item.childCount() == 1
    coordinate_item = sheet_item.child(0)
    assert coordinate_item is not None
    assert coordinate_item.text(0) == "座標：R1C1"
    assert coordinate_item.childCount() == 2
    dispose_window(window)


def test_gui_summary_distinguishes_full_and_selected_counts(
    qapp: QApplication, tmp_path: Path
) -> None:
    make_workbook(tmp_path / "rules.xlsx", "192.168.10.8")
    window = make_window(
        qapp,
        tmp_path,
        "# 目標清單\n"
        "192.168.10.0/24\n"
        "192.168.10.0/24\n"
        "192.168.10.8\n"
        "invalid-target\n",
    )
    rules = get_widget(window, QListWidget, "rule_selection_list")
    assert rules.count() == 4
    duplicate = rules.item(1)
    single = rules.item(2)
    assert duplicate is not None
    assert single is not None
    duplicate.setCheckState(Qt.CheckState.Unchecked)
    single.setCheckState(Qt.CheckState.Unchecked)

    spy = QSignalSpy(window.scan_finished)
    get_widget(window, QPushButton, "start_scan_button").click()
    wait_for_scan(spy)

    summary = get_widget(window, QLabel, "summary_label").text()
    assert "有效目標規則數：3" in summary
    assert "本次選取規則數：1" in summary
    assert "不同位址區間數：2" in summary
    assert "本次不同位址區間數：1" in summary
    assert "命中數：1" in summary
    dispose_window(window)
