"""
PySide6 图形界面 — 块属性批量填写工具主窗口

布局:
  顶部工具栏   → [选择块] 按钮
  属性编辑区   → 表格（复选框 + 标签名 + 输入框）
  文件管理区   → DWG 文件列表 + [载入DWG] [清空列表]
  操作区       → [开始处理] 按钮
  日志区       → 处理过程消息
"""
import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from batch_worker import BatchWorker
from cad_engine import CADEngine


# ===================================================================
# 主窗口
# ===================================================================
class MainWindow(QMainWindow):
    """主窗口。"""

    APP_TITLE = "块属性批量填写工具"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.APP_TITLE)
        self.setMinimumSize(900, 620)

        # ---- 数据状态 ------------------------------------------------
        self.block_info: dict[str, str] | None = None  # 最近选中的块信息
        self.dwg_files: list[str] = []                  # 待处理文件列表
        self.worker: BatchWorker | None = None          # 后台线程
        self._syncing_checks = False                    # 批量勾选防递归标志

        # ---- 构建 UI ------------------------------------------------
        self._build_ui()

    # ================================================================
    # UI 构建
    # ================================================================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)

        # -- 第 1 行：选择块 ------------------------------------------
        row1 = QHBoxLayout()
        self.btn_pick = QPushButton("🎯 选择块")
        self.btn_pick.setMinimumHeight(36)
        self.btn_pick.clicked.connect(self._on_pick_block)
        row1.addWidget(self.btn_pick)
        row1.addStretch()

        self.lbl_block = QLabel("尚未选择块")
        self.lbl_block.setStyleSheet("color: #666;")
        row1.addWidget(self.lbl_block)
        layout.addLayout(row1)

        # -- 第 2 行：属性编辑表格 ------------------------------------
        self.grp_attrs = QGroupBox("块属性（勾选 = 要处理的字段）")
        grp_layout = QVBoxLayout(self.grp_attrs)

        self.tbl_attrs = QTableWidget(0, 4)
        self.tbl_attrs.setHorizontalHeaderLabels(["处理", "属性标签", "提示词", "新值"])
        self.tbl_attrs.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tbl_attrs.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_attrs.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_attrs.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_attrs.verticalHeader().setVisible(False)
        self.tbl_attrs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_attrs.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_attrs.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.tbl_attrs.setMinimumHeight(120)
        self.tbl_attrs.itemChanged.connect(self._on_item_changed)
        grp_layout.addWidget(self.tbl_attrs)

        # -- 第 3 行：DWG 文件管理 ------------------------------------
        self.grp_files = QGroupBox("DWG 文件列表")
        fg_layout = QVBoxLayout(self.grp_files)

        btn_row = QHBoxLayout()
        self.btn_add_files = QPushButton("📂 载入 DWG")
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_remove_sel = QPushButton("✕ 删除选中")
        self.btn_remove_sel.clicked.connect(self._on_remove_selected)
        self.btn_clear_files = QPushButton("🗑 清空列表")
        self.btn_clear_files.clicked.connect(self._on_clear_files)
        self.lbl_file_count = QLabel("共 0 个文件")
        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_remove_sel)
        btn_row.addWidget(self.btn_clear_files)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_file_count)
        fg_layout.addLayout(btn_row)

        self.list_files = QListWidget()
        self.list_files.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list_files.setAlternatingRowColors(True)
        self.list_files.setMinimumHeight(80)
        fg_layout.addWidget(self.list_files)

        # -- 属性表 + 文件列表 左右并排 --------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.grp_attrs)
        splitter.addWidget(self.grp_files)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        # -- 第 4 行：进度条 + 操作按钮 -------------------------------
        op_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(24)
        op_row.addWidget(self.progress_bar, 1)

        self.btn_process = QPushButton("🚀 开始处理")
        self.btn_process.setMinimumHeight(36)
        self.btn_process.setMinimumWidth(140)
        self.btn_process.setStyleSheet(
            "QPushButton { background-color: #1976D2; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1565C0; }"
            "QPushButton:disabled { background-color: #B0BEC5; }"
        )
        self.btn_process.clicked.connect(self._on_start_process)
        self.btn_process.setEnabled(False)
        op_row.addWidget(self.btn_process)
        layout.addLayout(op_row)

        # -- 第 5 行：日志 -------------------------------------------
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("操作日志会显示在这里...")
        self.log.setMinimumHeight(100)
        self.log.setMaximumHeight(260)
        layout.addWidget(self.log, 1)

    # ================================================================
    # 事件处理
    # ================================================================

    def _on_pick_block(self):
        """点击『选择块』按钮 — 连接 CAD 并让用户点选块。"""
        self._log("🔄 正在连接 AutoCAD...")
        engine = CADEngine()
        if not engine.connect():
            QMessageBox.warning(
                self, "连接失败",
                "无法连接到 AutoCAD。\n请确认：\n"
                "1. AutoCAD 2026 已正确安装\n"
                "2. 至少手动启动过一次 AutoCAD（完成初始化）\n"
                "3. 当前有打开的 .dwg 文件"
            )
            self._log("❌ 连接 AutoCAD 失败")
            return

        self._log("✅ 已连接到 AutoCAD，请在图中点选一个带属性的块...")
        info = engine.pick_block()
        engine.close()

        if "_error" in info:
            QMessageBox.information(self, "提示", info["_error"])
            self._log(f"⚠ {info['_error']}")
            return

        # 成功读取块属性
        self.block_info = info
        block_name = info.get("__block_name__", "未知")
        self.lbl_block.setText(f"已选择块: {block_name}")
        self._log(f"✅ 已读取块 [{block_name}]，共 {len(info) - 1} 个属性")

        # 填充表格
        self._populate_attrs(info)
        self.btn_process.setEnabled(len(self.dwg_files) > 0)

    def _populate_attrs(self, info: dict[str, str | dict]):
        """将块属性填入表格。"""
        self.tbl_attrs.setRowCount(0)
        row = 0
        for tag, attr_data in info.items():
            if tag.startswith("__") and tag.endswith("__"):
                continue

            value = attr_data["value"]
            prompt = attr_data["prompt"]

            self.tbl_attrs.insertRow(row)

            # 列 0 — 复选框
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable
                         | Qt.ItemFlag.ItemIsEnabled
                         | Qt.ItemFlag.ItemIsSelectable)
            chk.setCheckState(Qt.CheckState.Checked)
            self.tbl_attrs.setItem(row, 0, chk)

            # 列 1 — 标签名（只读）
            tag_item = QTableWidgetItem(tag)
            tag_item.setFlags(Qt.ItemFlag.ItemIsEnabled
                              | Qt.ItemFlag.ItemIsSelectable)
            self.tbl_attrs.setItem(row, 1, tag_item)

            # 列 2 — 提示词（只读）
            prompt_item = QTableWidgetItem(prompt)
            prompt_item.setFlags(Qt.ItemFlag.ItemIsEnabled
                                 | Qt.ItemFlag.ItemIsSelectable)
            self.tbl_attrs.setItem(row, 2, prompt_item)

            # 列 3 — 输入框
            editor = QLineEdit(value)
            editor.setClearButtonEnabled(True)
            self.tbl_attrs.setCellWidget(row, 3, editor)

            row += 1

        self.tbl_attrs.resizeRowsToContents()

    def _on_item_changed(self, item: QTableWidgetItem):
        """复选框批量联动：勾选/取消一行时，所有选中行同步。"""
        if self._syncing_checks or item.column() != 0:
            return

        state = item.checkState()
        rows = set(i.row() for i in self.tbl_attrs.selectedItems())

        if len(rows) <= 1:
            return

        self._syncing_checks = True
        for r in rows:
            chk = self.tbl_attrs.item(r, 0)
            if chk is not None:
                chk.setCheckState(state)
        self._syncing_checks = False

    def _on_add_files(self):
        """点击『载入 DWG』按钮。"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择 DWG 文件",
            "",
            "DWG 文件 (*.dwg);;所有文件 (*)",
        )
        if not paths:
            return

        for p in paths:
            if p not in self.dwg_files:
                self.dwg_files.append(p)
                self.list_files.addItem(QListWidgetItem(p))

        self.lbl_file_count.setText(f"共 {len(self.dwg_files)} 个文件")
        self.btn_process.setEnabled(
            len(self.dwg_files) > 0 and self.block_info is not None
        )

    def _on_remove_selected(self):
        """删除选中的文件项。"""
        selected = self.list_files.selectedItems()
        if not selected:
            return
        # 从数据列表和 UI 列表中移除
        paths_to_remove = {item.text() for item in selected}
        self.dwg_files = [p for p in self.dwg_files if p not in paths_to_remove]
        for item in selected:
            row = self.list_files.row(item)
            self.list_files.takeItem(row)
        self.lbl_file_count.setText(f"共 {len(self.dwg_files)} 个文件")
        self.btn_process.setEnabled(
            len(self.dwg_files) > 0 and self.block_info is not None
        )

    def _on_clear_files(self):
        """清空文件列表。"""
        self.dwg_files.clear()
        self.list_files.clear()
        self.lbl_file_count.setText("共 0 个文件")
        self.btn_process.setEnabled(False)

    def _on_start_process(self):
        """点击『开始处理』按钮 — 启动后台批量处理。"""
        # ---- 收集用户输入 -------------------------------------------
        required_tags: list[str] = []
        values: dict[str, str] = {}

        for row in range(self.tbl_attrs.rowCount()):
            chk_item = self.tbl_attrs.item(row, 0)
            tag_item = self.tbl_attrs.item(row, 1)
            editor = self.tbl_attrs.cellWidget(row, 3)

            if chk_item is None or tag_item is None or editor is None:
                continue

            if chk_item.checkState() == Qt.CheckState.Checked:
                tag = tag_item.text()
                val = editor.text().strip()
                required_tags.append(tag)
                values[tag] = val

        if not required_tags:
            QMessageBox.warning(self, "提示", "请至少勾选一个要填写的属性字段。")
            return

        # ---- 确认对话框 ---------------------------------------------
        file_count = len(self.dwg_files)
        tag_names = ", ".join(required_tags)
        reply = QMessageBox.question(
            self,
            "确认处理",
            f"即将处理 {file_count} 个 DWG 文件。\n"
            f"勾选的属性字段: {tag_names}\n\n"
            f"⚠ 将直接覆盖原文件，不可撤销！\n是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # ---- 锁定 UI + 启动线程 -------------------------------------
        self._set_ui_busy(True)

        self.worker = BatchWorker(
            dwg_files=list(self.dwg_files),
            required_tags=required_tags,
            values=values,
        )
        self.worker.progress.connect(self._log)
        self.worker.file_done.connect(self._on_file_result)
        self.worker.all_done.connect(self._on_all_done)
        self.worker.start()

    # ================================================================
    # 批量处理回调
    # ================================================================

    def _on_file_result(self, result: dict):
        """单个文件处理完成。"""
        fname = os.path.basename(result.get("file", ""))
        err = result.get("error")
        if err:
            self._log(f"  ❌ {fname} — 出错: {err}")
        else:
            updated = result["updated"]
            skipped = result["skipped"]
            self._log(f"  ✅ {fname} — 更新 {updated} 个块，跳过 {skipped} 个")

    def _on_all_done(self):
        """全部处理完成。"""
        self._set_ui_busy(False)
        self.worker = None

    # ================================================================
    # 辅助方法
    # ================================================================

    def _log(self, msg: str):
        """在日志区追加一行。"""
        self.log.append(msg)
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log.setTextCursor(cursor)

    def _set_ui_busy(self, busy: bool):
        """处理期间禁用/启用控件。"""
        self.btn_pick.setEnabled(not busy)
        self.btn_add_files.setEnabled(not busy)
        self.btn_clear_files.setEnabled(not busy)
        self.btn_remove_sel.setEnabled(not busy)
        self.btn_process.setEnabled(not busy)
        self.progress_bar.setVisible(busy)
        if busy:
            self.progress_bar.setRange(0, 0)  # 忙碌动画
            self.btn_process.setText("⏳ 处理中...")
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.reset()
            self.btn_process.setText("🚀 开始处理")
