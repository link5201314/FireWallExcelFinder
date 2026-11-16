"""PySide6 離線防火牆 Excel 位址掃描介面。"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from audit_firewall_ips import (
    InputError,
    MatchRecord,
    ScanCancelled,
    ScanOutcome,
    ScanSummary,
    TargetRule,
    parse_target_lines,
    scan_directory,
    write_report,
)

LOGGER = logging.getLogger(__name__)
USER_ROLE_LINE = int(Qt.ItemDataRole.UserRole)
USER_ROLE_RAW = USER_ROLE_LINE + 1
USER_ROLE_VALID = USER_ROLE_LINE + 2


class ScanWorker(QThread):
    """在背景執行共用掃描流程並以 signals 回報狀態。"""

    completed = Signal(object)
    progress = Signal(int, int, str)

    def __init__(
        self,
        directory: Path,
        targets: list[TargetRule],
        recursive: bool,
        sheet_keywords: list[str] | None,
        verbose: bool,
        report_path: Path | None,
    ) -> None:
        super().__init__()
        self.directory = directory
        self.targets = targets
        self.recursive = recursive
        self.sheet_keywords = sheet_keywords
        self.verbose = verbose
        self.report_path = report_path
        self._cancel_requested = threading.Event()

    def cancel(self) -> None:
        """要求背景掃描在安全檢查點停止。"""
        self._cancel_requested.set()

    def report_progress(
        self, current: int, total: int, file_name: str
    ) -> None:
        """以 Qt signal 將進度安全送回主執行緒。"""
        self.progress.emit(current, total, file_name)

    def run(self) -> None:
        """掃描活頁簿，僅在未取消時原子提交報告。"""
        try:
            outcome = scan_directory(
                self.directory,
                self.targets,
                self.recursive,
                self.sheet_keywords,
                self._cancel_requested.is_set,
                self.report_progress,
            )
            if outcome.cancelled:
                self.completed.emit(outcome)
                return
            if self.report_path is not None:
                try:
                    write_report(
                        outcome.matches,
                        self.report_path,
                        self.verbose,
                        outcome.summary,
                        self._cancel_requested.is_set,
                        outcome.warnings,
                    )
                except ScanCancelled:
                    outcome.cancelled = True
                    outcome.matches.clear()
                except (InputError, OSError) as error:
                    outcome.report_error = f"無法寫入報告：{error}"
            self.completed.emit(outcome)
        except (InputError, OSError) as error:
            self.completed.emit(
                ScanOutcome(
                    [],
                    ScanSummary(0, len(self.targets), 0),
                    [],
                    error=f"掃描失敗：{error}",
                )
            )


class MainWindow(QMainWindow):
    """提供掃描設定、目標編輯與命中樹狀檢視的主視窗。"""

    scan_finished = Signal(bool)
    results_rendered = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("防火牆 Excel 位址掃描器")
        self.resize(1180, 820)
        self._worker: ScanWorker | None = None
        self._close_when_finished = False
        self._matches: list[MatchRecord] = []
        self._scan_result_available = False
        self._render_generation = 0
        self._render_index = 0
        self._render_maps: dict[
            str, dict[tuple[str, ...], QTreeWidgetItem]
        ] = {}
        self._saved_target_text = ""
        self._verbose = False
        self._accept_progress = False
        self._scan_controls: list[QWidget] = []
        self._build_ui()
        self._connect_signals()
        self._set_status("就緒")

        default_target_path = Path("targets.txt")
        self.target_file_input.setText(str(default_target_path))
        if default_target_path.is_file():
            self.load_targets()

    @property
    def scan_active(self) -> bool:
        """回報背景掃描是否仍在執行。"""
        return self._worker is not None and self._worker.isRunning()

    def _build_ui(self) -> None:
        """建立視窗控制項與版面配置。"""
        central = QWidget(self)
        root_layout = QVBoxLayout(central)

        settings_layout = QFormLayout()
        self.scan_directory_input = QLineEdit(str(Path.cwd()))
        self.scan_directory_input.setObjectName("scan_directory_input")
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.scan_directory_input)
        self.browse_directory_button = QPushButton("瀏覽…")
        self.browse_directory_button.setObjectName("browse_directory_button")
        directory_row.addWidget(self.browse_directory_button)
        settings_layout.addRow("Excel 目錄", directory_row)

        self.target_file_input = QLineEdit()
        self.target_file_input.setObjectName("target_file_input")
        target_path_row = QHBoxLayout()
        target_path_row.addWidget(self.target_file_input)
        self.browse_target_button = QPushButton("選擇…")
        self.browse_target_button.setObjectName("browse_target_button")
        self.load_targets_button = QPushButton("載入")
        self.load_targets_button.setObjectName("load_targets_button")
        self.save_targets_button = QPushButton("儲存")
        self.save_targets_button.setObjectName("save_targets_button")
        self.save_targets_as_button = QPushButton("另存新檔")
        self.save_targets_as_button.setObjectName("save_targets_as_button")
        target_path_row.addWidget(self.browse_target_button)
        target_path_row.addWidget(self.load_targets_button)
        target_path_row.addWidget(self.save_targets_button)
        target_path_row.addWidget(self.save_targets_as_button)
        settings_layout.addRow("目標規則檔", target_path_row)

        self.worksheet_keywords_input = QLineEdit()
        self.worksheet_keywords_input.setObjectName("worksheet_keywords_input")
        self.worksheet_keywords_input.setPlaceholderText(
            "以逗號分隔；空白代表全部工作表"
        )
        settings_layout.addRow("工作表關鍵字", self.worksheet_keywords_input)

        self.recursive_checkbox = QCheckBox("遞迴掃描子目錄")
        self.recursive_checkbox.setObjectName("recursive_checkbox")
        self.verbose_checkbox = QCheckBox("顯示完整儲存格文字")
        self.verbose_checkbox.setObjectName("verbose_checkbox")
        option_row = QHBoxLayout()
        option_row.addWidget(self.recursive_checkbox)
        option_row.addWidget(self.verbose_checkbox)
        settings_layout.addRow("掃描選項", option_row)

        self.report_format_combo = QComboBox()
        self.report_format_combo.setObjectName("report_format_combo")
        self.report_format_combo.addItems(["不輸出報告", "TXT", "CSV"])
        self.report_path_input = QLineEdit()
        self.report_path_input.setObjectName("report_path_input")
        self.report_path_input.setEnabled(False)
        self.browse_report_button = QPushButton("選擇報告路徑…")
        self.browse_report_button.setObjectName("browse_report_button")
        self.browse_report_button.setEnabled(False)
        report_row = QHBoxLayout()
        report_row.addWidget(self.report_format_combo)
        report_row.addWidget(self.report_path_input)
        report_row.addWidget(self.browse_report_button)
        settings_layout.addRow("報告輸出", report_row)
        root_layout.addLayout(settings_layout)

        target_layout = QHBoxLayout()
        self.target_editor = QPlainTextEdit()
        self.target_editor.setObjectName("target_editor")
        self.target_editor.setPlaceholderText(
            "每行輸入一條 IPv4、範圍或 CIDR；空白行與 # 註解會保留。"
        )
        target_layout.addWidget(self.target_editor, 3)
        rule_panel = QVBoxLayout()
        rule_panel.addWidget(QLabel("本次套用的有效目標規則"))
        self.rule_selection_list = QListWidget()
        self.rule_selection_list.setObjectName("rule_selection_list")
        rule_panel.addWidget(self.rule_selection_list)
        target_layout.addLayout(rule_panel, 2)
        root_layout.addLayout(target_layout, 2)

        control_row = QHBoxLayout()
        self.start_scan_button = QPushButton("開始掃描")
        self.start_scan_button.setObjectName("start_scan_button")
        self.cancel_scan_button = QPushButton("取消掃描")
        self.cancel_scan_button.setObjectName("cancel_scan_button")
        self.cancel_scan_button.setEnabled(False)
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.setObjectName("view_mode_combo")
        self.view_mode_combo.addItems(["檔案位置", "目標規則"])
        self.expand_all_button = QPushButton("全部展開")
        self.expand_all_button.setObjectName("expand_all_button")
        self.collapse_all_button = QPushButton("全部摺疊")
        self.collapse_all_button.setObjectName("collapse_all_button")
        control_row.addWidget(self.start_scan_button)
        control_row.addWidget(self.cancel_scan_button)
        control_row.addSpacing(16)
        control_row.addWidget(QLabel("檢視模式"))
        control_row.addWidget(self.view_mode_combo)
        control_row.addStretch(1)
        control_row.addWidget(self.expand_all_button)
        control_row.addWidget(self.collapse_all_button)
        root_layout.addLayout(control_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("scan_progress_bar")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        root_layout.addWidget(self.progress_bar)
        self.status_label = QLabel()
        self.status_label.setObjectName("status_label")
        self.summary_label = QLabel("尚未執行掃描")
        self.summary_label.setObjectName("summary_label")
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(self.summary_label)
        self.warnings_view = QPlainTextEdit()
        self.warnings_view.setObjectName("warnings_view")
        self.warnings_view.setReadOnly(True)
        self.warnings_view.setMaximumHeight(80)
        root_layout.addWidget(self.warnings_view)

        self.results_tree = QTreeWidget()
        self.results_tree.setObjectName("results_tree")
        self.results_tree.setHeaderLabels(["命中紀錄"])
        self.results_tree.setUniformRowHeights(True)
        self.empty_results_label = QLabel("沒有符合的命中紀錄")
        self.empty_results_label.setObjectName("empty_results_label")
        self.empty_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_results_label.hide()
        root_layout.addWidget(self.empty_results_label, 3)
        root_layout.addWidget(self.results_tree, 3)
        self.setCentralWidget(central)
        self._scan_controls = [
            self.scan_directory_input,
            self.browse_directory_button,
            self.target_file_input,
            self.browse_target_button,
            self.load_targets_button,
            self.save_targets_button,
            self.save_targets_as_button,
            self.worksheet_keywords_input,
            self.recursive_checkbox,
            self.verbose_checkbox,
            self.report_format_combo,
            self.report_path_input,
            self.browse_report_button,
            self.target_editor,
            self.rule_selection_list,
            self.view_mode_combo,
        ]

    def _connect_signals(self) -> None:
        """連接使用者操作與視窗行為。"""
        self.browse_directory_button.clicked.connect(self.browse_directory)
        self.browse_target_button.clicked.connect(self.browse_target_file)
        self.load_targets_button.clicked.connect(self.load_targets)
        self.save_targets_button.clicked.connect(self.save_targets)
        self.save_targets_as_button.clicked.connect(self.save_targets_as)
        self.browse_report_button.clicked.connect(self.browse_report_path)
        self.report_format_combo.currentIndexChanged.connect(
            self._report_format_changed
        )
        self.target_editor.textChanged.connect(self._refresh_rule_selection)
        self.target_editor.textChanged.connect(
            self._update_target_dirty_status
        )
        self.start_scan_button.clicked.connect(self.start_scan)
        self.cancel_scan_button.clicked.connect(self.cancel_scan)
        self.view_mode_combo.currentIndexChanged.connect(self._render_results)
        self.expand_all_button.clicked.connect(self.results_tree.expandAll)
        self.collapse_all_button.clicked.connect(self.results_tree.collapseAll)

    def _set_status(self, message: str) -> None:
        """更新介面狀態文字。"""
        self.status_label.setText(message)

    def _update_target_dirty_status(self) -> None:
        """顯示目標文字是否尚未儲存。"""
        if self.target_editor.toPlainText() != self._saved_target_text:
            self._set_status("目標規則有未儲存修改")
        elif not self.scan_active:
            self._set_status("就緒")

    def browse_directory(self) -> None:
        """選擇 Excel 掃描目錄。"""
        selected = QFileDialog.getExistingDirectory(
            self, "選擇 Excel 掃描目錄", self.scan_directory_input.text()
        )
        if selected:
            self.scan_directory_input.setText(selected)

    def browse_target_file(self) -> None:
        """選擇要載入或儲存的目標規則檔。"""
        if not self._confirm_target_edit_transition("選擇其他目標檔"):
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "選擇目標規則檔",
            self.target_file_input.text(),
            "文字檔 (*.txt);;所有檔案 (*)",
        )
        if selected:
            self.target_file_input.setText(selected)
            self.load_targets()

    def load_targets(self) -> None:
        """載入目標規則文字檔並重設未儲存狀態。"""
        if not self._confirm_target_edit_transition("載入其他目標檔"):
            return
        path_text = self.target_file_input.text().strip()
        if not path_text:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "載入目標規則檔",
                str(Path.cwd()),
                "文字檔 (*.txt);;所有檔案 (*)",
            )
            if not selected:
                return
            path_text = selected
            self.target_file_input.setText(selected)
        try:
            contents = Path(path_text).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            self._set_status(f"無法載入目標規則檔：{error}")
            return
        self.target_editor.setPlainText(contents)
        self._saved_target_text = self.target_editor.toPlainText()
        self.target_editor.document().setModified(False)
        self._refresh_rule_selection()
        self._set_status(f"已載入目標規則：{path_text}")

    def _write_targets(self, path: Path, success_message: str) -> bool:
        """將目前目標文字寫入指定路徑並重設未儲存狀態。"""
        try:
            path.write_text(
                self.target_editor.toPlainText(), encoding="utf-8", newline=""
            )
        except OSError as error:
            self._set_status(f"無法儲存目標規則檔：{error}")
            return False
        self._saved_target_text = self.target_editor.toPlainText()
        self.target_editor.document().setModified(False)
        self._set_status(success_message)
        return True

    def save_targets(self) -> bool:
        """儲存目標文字，沒有檔案路徑時要求另存新檔。"""
        path_text = self.target_file_input.text().strip()
        if not path_text:
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "另存目標規則檔",
                str(Path.cwd() / "targets.txt"),
                "文字檔 (*.txt)",
            )
            if not selected:
                self._set_status("已取消儲存，未開始掃描")
                return False
            path_text = selected
            self.target_file_input.setText(path_text)
        path = Path(path_text)
        if not path.suffix:
            path = path.with_suffix(".txt")
            self.target_file_input.setText(str(path))
        return self._write_targets(path, f"已儲存目標規則：{path}")

    def save_targets_as(self) -> bool:
        """將目前目標文字另存到使用者選擇的新檔案。"""
        path_text = self.target_file_input.text().strip()
        initial_path = (
            path_text if path_text else str(Path.cwd() / "targets.txt")
        )
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "另存目標規則檔",
            initial_path,
            "文字檔 (*.txt)",
        )
        if not selected:
            self._set_status("已取消另存新檔")
            return False
        path = Path(selected)
        if not path.suffix:
            path = path.with_suffix(".txt")
        if not self._write_targets(path, f"已另存目標規則：{path}"):
            return False
        self.target_file_input.setText(str(path))
        return True

    def _confirm_target_edit_transition(self, action: str) -> bool:
        """在載入新檔或離開前，確認未儲存目標修改的處置。"""
        if self.target_editor.toPlainText() == self._saved_target_text:
            return True
        choice = QMessageBox.question(
            self,
            "目標規則尚未儲存",
            f"目標規則有未儲存修改。是否先儲存，再{action}？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save_targets()
        return choice == QMessageBox.StandardButton.Discard

    def browse_report_path(self) -> None:
        """選擇 TXT 或 CSV 報告輸出位置。"""
        extension = (
            ".csv" if self.report_format_combo.currentIndex() == 2 else ".txt"
        )
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "選擇報告輸出位置",
            str(Path.cwd() / f"report{extension}"),
            "CSV 報告 (*.csv);;文字報告 (*.txt)",
        )
        if selected:
            self.report_path_input.setText(selected)

    def _report_format_changed(self, index: int) -> None:
        """依報告格式切換路徑欄位。"""
        enabled = index != 0
        self.report_path_input.setEnabled(enabled)
        self.browse_report_button.setEnabled(enabled)

    def _set_scan_controls_enabled(self, enabled: bool) -> None:
        """依掃描狀態及報告格式更新設定控制項。"""
        for control in self._scan_controls:
            control.setEnabled(enabled)
        if enabled:
            self._report_format_changed(
                self.report_format_combo.currentIndex()
            )

    def _refresh_rule_selection(self) -> None:
        """依編輯內容驗證規則，保留仍存在規則的勾選狀態。"""
        previous_selection: dict[tuple[int, str], bool] = {}
        for index in range(self.rule_selection_list.count()):
            item = self.rule_selection_list.item(index)
            if item.data(USER_ROLE_VALID):
                key = (item.data(USER_ROLE_LINE), item.data(USER_ROLE_RAW))
                previous_selection[key] = (
                    item.checkState() == Qt.CheckState.Checked
                )

        lines = self.target_editor.toPlainText().splitlines()
        rules, issues = parse_target_lines(lines)
        rules_by_line = {rule.line_number: rule for rule in rules}
        issues_by_line = {issue.line_number: issue for issue in issues}
        self.rule_selection_list.clear()
        for line_number in sorted(
            (*rules_by_line.keys(), *issues_by_line.keys())
        ):
            rule = rules_by_line.get(line_number)
            if rule is not None:
                item = QListWidgetItem(f"第 {line_number} 行：{rule.raw}")
                item.setData(USER_ROLE_LINE, line_number)
                item.setData(USER_ROLE_RAW, rule.raw)
                item.setData(USER_ROLE_VALID, True)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                checked = previous_selection.get((line_number, rule.raw), True)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if checked
                    else Qt.CheckState.Unchecked
                )
            else:
                issue = issues_by_line[line_number]
                item = QListWidgetItem(
                    f"第 {line_number} 行：{issue.raw}"
                    f"（格式錯誤：{issue.message}）"
                )
                item.setData(USER_ROLE_LINE, line_number)
                item.setData(USER_ROLE_RAW, issue.raw)
                item.setData(USER_ROLE_VALID, False)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
            self.rule_selection_list.addItem(item)

    def _selected_targets(self) -> list[TargetRule]:
        """取得介面中已勾選的有效目標規則。"""
        selected: set[tuple[int, str]] = set()
        for index in range(self.rule_selection_list.count()):
            item = self.rule_selection_list.item(index)
            if (
                item.data(USER_ROLE_VALID)
                and item.checkState() == Qt.CheckState.Checked
            ):
                selected.add(
                    (item.data(USER_ROLE_LINE), item.data(USER_ROLE_RAW))
                )
        rules, _ = parse_target_lines(
            self.target_editor.toPlainText().splitlines()
        )
        return [
            rule for rule in rules if (rule.line_number, rule.raw) in selected
        ]

    def _parse_sheet_keywords(self) -> list[str] | None:
        """解析逗號、分號或換行分隔的工作表關鍵字。"""
        raw = self.worksheet_keywords_input.text()
        keywords = [
            part.strip()
            for part in raw.replace(";", ",").split(",")
            if part.strip()
        ]
        return keywords or None

    def _ensure_saved_targets(self) -> list[TargetRule] | None:
        """確保目標文字先成功保存，再以保存內容建立本次規則。"""
        all_rules, _ = parse_target_lines(
            self.target_editor.toPlainText().splitlines()
        )
        if not all_rules:
            self._set_status("目標清單沒有有效規則，未開始掃描")
            return None
        selected_keys = {
            (rule.line_number, rule.raw) for rule in self._selected_targets()
        }
        if not selected_keys:
            self._set_status("沒有已選取的有效目標規則，未開始掃描")
            return None

        path_text = self.target_file_input.text().strip()
        target_path = Path(path_text) if path_text else None
        needs_save = (
            self.target_editor.toPlainText() != self._saved_target_text
            or target_path is None
            or not target_path.is_file()
        )
        if needs_save and not self.save_targets():
            return None

        saved_path = Path(self.target_file_input.text().strip())
        try:
            saved_text = saved_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            self._set_status(f"無法確認已儲存的目標規則：{error}")
            return None
        saved_rules, issues = parse_target_lines(saved_text.splitlines())
        if issues:
            self._set_status(
                f"目標檔有 {len(issues)} 行格式錯誤；已略過並繼續使用有效規則"
            )
        selected_rules = [
            rule
            for rule in saved_rules
            if (rule.line_number, rule.raw) in selected_keys
        ]
        if not selected_rules:
            self._set_status("儲存後找不到已選取規則，未開始掃描")
            return None
        return selected_rules

    def start_scan(self) -> None:
        """驗證設定、保存目標並啟動背景掃描。"""
        if self.scan_active:
            self._set_status("掃描進行中，請先等待或取消")
            return
        targets = self._ensure_saved_targets()
        if not targets:
            return

        directory_text = self.scan_directory_input.text().strip()
        if not directory_text or not Path(directory_text).is_dir():
            self._set_status("Excel 掃描目錄不存在或不是目錄，未開始掃描")
            QMessageBox.warning(self, "掃描目錄無效", self.status_label.text())
            return

        report_path = self._selected_report_path()
        if report_path is False:
            return

        self.results_tree.clear()
        self._matches.clear()
        self._scan_result_available = False
        self.empty_results_label.hide()
        self.results_tree.show()
        self.warnings_view.clear()
        self.summary_label.setText("掃描中…")
        self.progress_bar.setRange(0, 0)
        self._set_status("正在背景掃描 Excel 活頁簿…")
        self.start_scan_button.setEnabled(False)
        self.cancel_scan_button.setEnabled(True)
        self._set_scan_controls_enabled(False)
        self._worker = ScanWorker(
            Path(directory_text),
            targets,
            self.recursive_checkbox.isChecked(),
            self._parse_sheet_keywords(),
            self.verbose_checkbox.isChecked(),
            report_path if isinstance(report_path, Path) else None,
        )
        self._verbose = self.verbose_checkbox.isChecked()
        self._accept_progress = True
        self._worker.progress.connect(self._update_progress)
        self._worker.completed.connect(self._handle_scan_completed)
        self._worker.finished.connect(self._release_worker)
        self._worker.start()

    def _selected_report_path(self) -> Path | None | bool:
        """驗證輸出設定並取得報告路徑；False 表示使用者取消操作。"""
        index = self.report_format_combo.currentIndex()
        if index == 0:
            return None
        extension = ".txt" if index == 1 else ".csv"
        path_text = self.report_path_input.text().strip()
        if not path_text:
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "選擇報告輸出位置",
                str(Path.cwd() / f"report{extension}"),
                "CSV 報告 (*.csv);;文字報告 (*.txt)",
            )
            if not selected:
                self._set_status("已取消選擇報告路徑，未開始掃描")
                return False
            path_text = selected
            self.report_path_input.setText(path_text)
        path = Path(path_text)
        if path.suffix.casefold() != extension:
            if not path.suffix:
                path = path.with_suffix(extension)
                self.report_path_input.setText(str(path))
            else:
                self._set_status(f"報告副檔名必須是 {extension}")
                return False
        target_path_text = self.target_file_input.text().strip()
        if target_path_text:
            try:
                if path.resolve() == Path(target_path_text).resolve():
                    self._set_status("報告路徑不可與目標規則檔相同")
                    return False
            except OSError as error:
                self._set_status(f"無法驗證報告路徑：{error}")
                return False
        return path

    def cancel_scan(self) -> None:
        """向背景工作送出取消要求。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self.cancel_scan_button.setEnabled(False)
            self._set_status("正在取消掃描…")

    def _update_progress(
        self, current: int, total: int, file_name: str
    ) -> None:
        """更新目前掃描檔案與進度。"""
        if not self._accept_progress:
            return
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self._set_status(f"掃描中：{file_name}（{current}/{total}）")

    def _handle_scan_completed(self, outcome: ScanOutcome) -> None:
        """呈現掃描完成、取消或錯誤結果。"""
        self._accept_progress = False
        self.start_scan_button.setEnabled(True)
        self.cancel_scan_button.setEnabled(False)
        self._set_scan_controls_enabled(True)
        self.progress_bar.setRange(0, max(outcome.summary.files_scanned, 1))
        self.progress_bar.setValue(
            0 if outcome.cancelled else outcome.summary.files_scanned
        )
        if outcome.error:
            self._matches.clear()
            self._scan_result_available = False
            self.results_tree.clear()
            self.empty_results_label.hide()
            self.results_tree.show()
            self.summary_label.setText("掃描未完成")
            self._set_status(outcome.error)
            self.scan_finished.emit(False)
            return
        if outcome.cancelled:
            self._matches.clear()
            self._scan_result_available = False
            self.results_tree.clear()
            self.empty_results_label.hide()
            self.results_tree.show()
            self.summary_label.setText("掃描已取消；未保留部分結果")
            self._set_status("掃描已取消，未提交報告")
            self.scan_finished.emit(True)
            return

        self._matches = outcome.matches
        self._scan_result_available = True
        self._render_results()
        self._render_summary(outcome)
        warnings = list(outcome.warnings)
        if outcome.report_error:
            warnings.append(outcome.report_error)
        self.warnings_view.setPlainText("\n".join(warnings))
        if outcome.report_error:
            self._set_status(f"掃描完成，但{outcome.report_error}")
        elif outcome.summary.partial_failure:
            self._set_status("掃描完成，但有部分檔案或目錄無法讀取")
        else:
            self._set_status("掃描完成")
        self.scan_finished.emit(False)

    def _render_summary(self, outcome: ScanOutcome) -> None:
        """呈現目標規則、位址區間與命中統計。"""
        all_rules, _ = parse_target_lines(
            self.target_editor.toPlainText().splitlines()
        )
        all_intervals = {
            (rule.interval.start, rule.interval.end) for rule in all_rules
        }
        selected_rules = self._selected_targets()
        selected_intervals = {
            (rule.interval.start, rule.interval.end) for rule in selected_rules
        }
        summary = outcome.summary
        self.summary_label.setText(
            f"掃描檔案數：{summary.files_scanned}　"
            f"有效目標規則數：{len(all_rules)}　"
            f"本次選取規則數：{len(selected_rules)}　"
            f"不同位址區間數：{len(all_intervals)}　"
            f"本次不同位址區間數：{len(selected_intervals)}　"
            f"命中數：{len(outcome.matches)}　"
            f"部分失敗：{'是' if summary.partial_failure else '否'}"
        )

    def _render_results(self) -> None:
        """依目前模式重建樹狀檢視，不重新掃描活頁簿。"""
        self._render_generation += 1
        generation = self._render_generation
        self._render_index = 0
        self.results_tree.clear()
        has_results = bool(self._matches)
        self.results_tree.setVisible(has_results)
        self.empty_results_label.setVisible(
            self._scan_result_available and not has_results
        )
        if not has_results:
            if self._scan_result_available:
                self.results_rendered.emit()
            return
        mode = self.view_mode_combo.currentIndex()
        self._render_maps = {
            "files": {},
            "sheets": {},
            "coordinates": {},
            "targets": {},
            "target_files": {},
            "target_sheets": {},
            "target_coordinates": {},
        }
        QTimer.singleShot(
            0, lambda: self._render_result_chunk(generation, mode)
        )

    def _render_result_chunk(self, generation: int, mode: int) -> None:
        """分批加入命中節點，讓 GUI 事件迴圈持續回應。"""
        if generation != self._render_generation:
            return
        stop_index = min(self._render_index + 100, len(self._matches))
        while self._render_index < stop_index:
            record = self._matches[self._render_index]
            if mode == 0:
                self._add_file_record(record)
            else:
                self._add_target_record(record)
            self._render_index += 1

        if self._render_index < len(self._matches):
            QTimer.singleShot(
                0, lambda: self._render_result_chunk(generation, mode)
            )
            return
        self.results_tree.expandToDepth(1)
        self.results_rendered.emit()

    def _child_item(
        self,
        parent: QTreeWidget | QTreeWidgetItem,
        map_name: str,
        key: tuple[str, ...],
        label: str,
    ) -> QTreeWidgetItem:
        """取得或建立樹狀節點，並依指定鍵快取。"""
        items = self._render_maps[map_name]
        item = items.get(key)
        if item is None:
            item = QTreeWidgetItem(parent, [label])
            items[key] = item
        return item

    def _add_file_record(self, record: MatchRecord) -> None:
        """將一筆命中加入檔案位置樹的共用節點。"""
        file_item = self._child_item(
            self.results_tree,
            "files",
            (record.file_name,),
            f"檔案：{record.file_name}",
        )
        sheet_item = self._child_item(
            file_item,
            "sheets",
            (record.file_name, record.sheet),
            f"工作表：{record.sheet}",
        )
        coordinate_item = self._child_item(
            sheet_item,
            "coordinates",
            (record.file_name, record.sheet, record.coordinate),
            f"座標：{record.coordinate}",
        )
        self._add_match_detail(coordinate_item, record)

    def _add_target_record(self, record: MatchRecord) -> None:
        """將一筆命中加入目標規則樹的共用節點。"""
        target_key = (str(record.target.line_number), record.target.raw)
        root_item = self._child_item(
            self.results_tree,
            "targets",
            target_key,
            f"目標第 {record.target.line_number} 行：{record.target.raw}",
        )
        file_key = (*target_key, record.file_name)
        file_item = self._child_item(
            root_item,
            "target_files",
            file_key,
            f"檔案：{record.file_name}",
        )
        sheet_key = (*file_key, record.sheet)
        sheet_item = self._child_item(
            file_item,
            "target_sheets",
            sheet_key,
            f"工作表：{record.sheet}",
        )
        coordinate_item = self._child_item(
            sheet_item,
            "target_coordinates",
            (*sheet_key, record.coordinate),
            f"座標：{record.coordinate}",
        )
        self._add_match_detail(coordinate_item, record)

    def _add_match_detail(
        self, parent: QTreeWidgetItem, record: MatchRecord
    ) -> None:
        """加入可追溯目標、Token 與上下文的命中明細。"""
        context = record.cell_text if self._verbose else record.context
        detail = (
            f"目標第 {record.target.line_number} 行：{record.target.raw} | "
            f"Token：{record.token} | 上下文：{context}"
        )
        item = QTreeWidgetItem(parent, [detail])
        item.setToolTip(0, f"完整儲存格內容：{record.cell_text}")

    def _release_worker(self) -> None:
        """在 Qt 背景執行緒結束後釋放工作物件。"""
        worker = self._worker
        if worker is not None and not worker.isRunning():
            self._worker = None
            if self._close_when_finished:
                self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        """關閉視窗前安全取消仍在執行的背景掃描。"""
        if self.scan_active:
            self._close_when_finished = True
            self.cancel_scan()
            event.ignore()
            return
        if not self._confirm_target_edit_transition("關閉程式"):
            event.ignore()
            return
        event.accept()


def main() -> int:
    """啟動 PySide6 桌面應用程式。"""
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s: %(message)s"
    )
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
